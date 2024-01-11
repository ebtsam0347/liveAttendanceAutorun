from zk import ZK
import pyodbc
import threading
import re
from datetime import datetime
import sys
import getpass
import msvcrt

# devices = []
def get_input(prompt):
    while True:
        user_input = input(prompt).strip()
        if user_input:
            return user_input
        else:
            print("Input cannot be empty.")
            
def get_masked_input(prompt, mask_char='#'):
    input_text = ""
    print(prompt, end='', flush=True)

    while True:
        key = msvcrt.getch().decode('utf-8')
        if key == '\r':
            break
        elif key == '\b':
            if input_text:
                input_text = input_text[:-1]
                print('\b \b', end='', flush=True)  # Clear the last character on the screen
        else:
            input_text += key
            print(mask_char, end='', flush=True)

    print()  # Move to the next line after the user hits enter
    return input_text

def database_connection():
    while True:
        try:
            server = get_input("\nEnter server address: ")
            database = get_input("Enter database name: ")
            username = get_input("Enter username: ")
            # password = getpass.getpass(prompt='Enter your password: ')
            password = get_masked_input("Enter your password: ", mask_char='#')
            conn = pyodbc.connect(
                f'DRIVER={{ODBC Driver 17 for SQL Server}};'
                f'SERVER={server};'
                f'DATABASE={database};'
                f'UID={username};'
                f'PWD={password}'
            )

            print('Connected to the database')            
            return conn

        except Exception as e:
            print(f'Error connecting to the database: {str(e)}')

            retry = input("Do you want to retry? (y/n): ").lower()
            if retry != 'y':
                restart = input("Do you want to restart input? (y/n): ").lower()
                if restart != 'y':
                    sys.exit("Table name not provided. Exiting the script.")
                    return None
                else:
                    print("Restarting input...")
                    continue
            else:
                print("Restarting input...")
                continue

def table_exists(db_conn, table_name):
    while True:
        try:
            cursor = db_conn.cursor()
            cursor.execute(f"SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = '{table_name}'")
            return cursor.fetchone() is not None
        except Exception as e:
            print(f"Error checking table existence: {str(e)}")
            return False
        # finally:
        #     cursor.close()
        
def devices_from_database(db_conn, table_name):
     while True:
        try:
            sql_select = f"SELECT DeviceIp FROM {table_name}"

            cursor = db_conn.cursor()
            cursor.execute(sql_select)
            rows = cursor.fetchall()
            devices = [row[0] for row in rows if row[0] is not None]
            return devices
        except Exception as e:
            print(f"Error getting devices from table: {str(e)}")

            retry = input("Do you want to retry getting devices? (y/n): ").lower()
            if retry != 'y':
                return []

def capture_attendance(DeviceIp, stop_event, db_conn, table_name):
    while not stop_event.is_set():
        try:
            zk = ZK(DeviceIp, port=4370)
            conn = zk.connect()

            if conn:
                print(f'Connected with {DeviceIp}\n')
                device_name = zk.get_device_name()

            for attendance in conn.live_capture():
                if attendance is None:
                    continue  # Skip None values and keep capturing

                attendance_string = str(attendance)
                match = re.search(r': (\d+) : (.*?) \(', attendance_string)
                if match:
                    duser_id = match.group(1)
                    dtime_str = match.group(2)
                    dtime = datetime.strptime(dtime_str, '%Y-%m-%d %H:%M:%S')
                else:
                    print("User ID or Timestamp not found in the attendance string")

                print(attendance,"with",DeviceIp,"\n")  # Attendance object

                cursor = db_conn.cursor()
                cursor.execute(
                    f"INSERT INTO {table_name} (user_id, datetime, device_name, device_ip, status) "
                    f"VALUES ('{duser_id}', '{dtime}', '{device_name}', '{DeviceIp}', '{1}' )"
                )
                db_conn.commit()
                print("Saved into Database\n--------\n")
                cursor.close()

        except Exception as e:
            print(f'Error for {DeviceIp} capturing attendance: {str(e)}')
            continue

    # finally:
    #     db_conn.close()

# Your list of devices

if __name__ == '__main__':
    db_conn = database_connection()
    if db_conn:
        while True:
            table_name = get_input("Enter the table name for attendance where you want to save attendance: ")
            if table_exists(db_conn, table_name):
                print(f"The table '{table_name}' exists.")
                break
            else:
                retry = input("Table not Found.\nDo you want to retry entering the table name? (y/n): ").lower()
                if retry != 'y':
                    sys.exit("Table name not provided. Exiting the script.")
            
        while True:
            devices_table_name = get_input("Enter the table name for attendance where you get device table: ")
            if table_exists(db_conn, devices_table_name):
                print(f"The table '{devices_table_name}' exists.")
                break
            else:
                retry = input("Do you want to retry entering the table name? (y/n): ").lower()
                if retry != 'y':
                    sys.exit("Table name not provided. Exiting the script.")
                    
                
    if not db_conn:
        sys.exit("Unable to establish a database connection.")

    threads = []
    stop_event = threading.Event()

    try:
        devices_from_database(db_conn,devices_table_name)
        devices = devices_from_database(db_conn,devices_table_name)
        print(f"{len(devices)} devices are connecting now...")
        for device_ip in devices:
            t = threading.Thread(target=capture_attendance, args=(device_ip, stop_event, db_conn,table_name))
            t.start()
            threads.append(t)

        # Keep the main thread running to allow Ctrl+C to stop the script
        while True:
            pass

    except KeyboardInterrupt:
        # Set the stop_event to stop all threads
        stop_event.set()

        # Wait for all threads to finish
        for t in threads:
            t.join()

        sys.exit("Script terminated by user.")
