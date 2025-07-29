import asyncio
import os
import re
import sys
import configparser
import webbrowser
import time
from getpass import getpass
from datetime import datetime, timezone
from telethon import TelegramClient
from telethon.tl.types import Message

if getattr(sys, 'frozen', False):
    SCRIPT_DIR = os.path.dirname(sys.executable)
else:
    try:
        SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        SCRIPT_DIR = os.getcwd()

DOWNLOAD_FOLDER = os.path.join(SCRIPT_DIR, 'Telegram Downloads')
SESSION_FILE_NAME = 'Session'
SESSION_PATH = os.path.join(SCRIPT_DIR, SESSION_FILE_NAME) 
CONFIG_FILE = os.path.join(SCRIPT_DIR, 'Config.ini')

def load_or_request_config():
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)
        if 'telegram' not in config or 'api_id' not in config['telegram'] or 'api_hash' not in config['telegram']:
            print(f"ERROR: '{CONFIG_FILE}' is corrupt or incomplete. Please reset the configuration from the main menu.")
            return None, None, False
        api_id = config['telegram']['api_id']
        api_hash = config['telegram']['api_hash']
        from_file = True
        return api_id, api_hash, from_file
    else:
        print("Telegram API details not found. Please enter the following information.")
        url = "https://my.telegram.org"
        print(f"You can get this information from: \033]8;;{url}\a{url}\033]8;;\a")
        try:
            print("Trying to open the link in your default browser...")
            webbrowser.open(url)
        except Exception:
            print("Browser could not be opened automatically. Please copy and paste the link manually.")
        
        api_id_str = input("Please enter your API ID: ").strip()
        api_hash = input("Please enter your API HASH: ").strip()
        
        if not api_id_str or not api_hash:
            print("\nERROR: API ID and API HASH cannot be empty.")
            return None, None, False

        from_file = False
        return api_id_str, api_hash, from_file

def get_validated_phone():
    while True:
        phone = input("Please enter your phone number (e.g., +15551234567): ")
        if phone.startswith('+') and phone[1:].isdigit():
            return phone
        else:
            print("\nERROR: Invalid format! The number must start with '+' followed by the country code.")

async def download_message_media(client, message, download_path=None):
    if not message or not message.media:
        if message: print("This post does not contain any downloadable media.")
        else: print("Error: Message not found or link is invalid.")
        return

    final_download_folder = download_path or DOWNLOAD_FOLDER
    
    start_time = time.time()
    def format_speed(speed_bytes_per_sec):
        if speed_bytes_per_sec < 1024 * 1024: return f"{speed_bytes_per_sec / 1024:.2f} KB/s"
        else: return f"{speed_bytes_per_sec / (1024 * 1024):.2f} MB/s"

    def progress_callback(current, total):
        elapsed_seconds = time.time() - start_time
        speed = (current / elapsed_seconds) if elapsed_seconds > 0 else 0
        speed_str = format_speed(speed)
        mins, secs = divmod(int(elapsed_seconds), 60)
        elapsed_time_str = f"{mins:02d}:{secs:02d}"
        percentage = (current / total) * 100
        bar = '[' + '█' * int(percentage // 5) + ' ' * (20 - int(percentage // 5)) + ']'
        current_mb, total_mb = current / (1024*1024), total / (1024*1024)
        print(f"\rDownloading: {bar} {percentage:.1f}% ({current_mb:.2f}/{total_mb:.2f} MB) | Speed: {speed_str} | Elapsed Time: {elapsed_time_str}", end='')

    try:
        file_path = await client.download_media(message.media, file=final_download_folder, progress_callback=progress_callback)
        print(f"\nDownload complete! File saved to: {file_path}")
    except Exception as e:
        print(f"\nAn error occurred during download: {e}")

async def process_link(client, link):
    print(f"\nProcessing: {link.strip()}")
    match = re.match(r'https://t\.me/(c/)?([\w\d_]+)/(\d+)', link)
    if not match:
        print("Error: Invalid Telegram link format. Skipping this link.")
        return
    try:
        channel_identifier_str = match.group(2)
        msg_id = int(match.group(3))
        channel_identifier = channel_identifier_str
        if match.group(1):
            try: channel_identifier = int(f"-100{channel_identifier_str}")
            except ValueError: pass
        target_entity = await client.get_entity(channel_identifier)
        message = await client.get_messages(target_entity, ids=msg_id)
        await download_message_media(client, message)
    except Exception as e:
        print(f"ERROR: An error occurred while processing the link. Details: {e}")

async def handle_link_download(client):
    user_input = input("\nEnter a link or the path to a .txt file containing links: ")
    cleaned_input = user_input.strip().strip('\'"')
    links_to_download = []
    if cleaned_input.lower().endswith('.txt'):
        if os.path.exists(cleaned_input):
            with open(cleaned_input, 'r', encoding='utf-8') as f: links_to_download = [line.strip() for line in f if line.strip()]
            print(f"{len(links_to_download)} links found in '{cleaned_input}'.")
        else:
            print(f"ERROR: File not found: '{cleaned_input}'.")
            return
    else:
        links_to_download.append(cleaned_input)
    total_links = len(links_to_download)
    for i, link in enumerate(links_to_download, 1):
        if total_links > 1: print(f"\n--- Batch Download ({i}/{total_links}) ---")
        await process_link(client, link)
    if total_links > 1: print("\n--- Batch download complete! ---")

async def handle_channel_download(client):
    channel_input = input("\nEnter the channel link or @username to download all its media: ").strip()
    try:
        target_entity = await client.get_entity(channel_input)
        safe_channel_name = re.sub(r'[\\/*?:"<>|]', "", target_entity.title)
        channel_folder = os.path.join(DOWNLOAD_FOLDER, safe_channel_name)
        os.makedirs(channel_folder, exist_ok=True)
        print(f"Downloaded files will be saved to: {channel_folder}")
    except Exception as e:
        print(f"ERROR: Channel not found or could not be accessed. Details: {e}")
        return

    media_filter = input("Which media types to download? (all, photo, video, file) [all]: ").lower().strip() or "all"
    
    start_date = None
    while True:
        start_date_str = input("Start date (YYYY-MM-DD - leave empty to start from the beginning): ").strip()
        if not start_date_str: break
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            break
        except ValueError: print("ERROR: Invalid date format. Please use YYYY-MM-DD (e.g., 2023-12-25).")

    end_date = None
    while True:
        end_date_str = input("End date (YYYY-MM-DD - leave empty to go to the end): ").strip()
        if not end_date_str: break
        try:
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            break
        except ValueError: print("ERROR: Invalid date format. Please use YYYY-MM-DD (e.g., 2024-01-15).")
    
    count, downloaded_count = 0, 0
    print("\nScanning channel history... This might take a long time depending on the channel size.")
    try:
        async for message in client.iter_messages(target_entity, reverse=True, offset_date=start_date):
            count += 1
            if count % 100 == 0: print(f"\rScanned messages: {count}, Downloaded media: {downloaded_count}", end="")
            if end_date and message.date > end_date:
                print("\nReached the specified end date. Stopping scan.")
                break
            if message.media:
                is_photo = message.photo is not None
                is_video = message.video is not None or (hasattr(message.document, 'mime_type') and 'video' in message.document.mime_type)
                is_document = message.document is not None and not is_video
                should_download = (media_filter == 'all' or (media_filter == 'photo' and is_photo) or (media_filter == 'video' and is_video) or (media_filter == 'file' and is_document))
                if should_download:
                    print(f"\n(Media found #{downloaded_count + 1} - Message Date: {message.date.strftime('%Y-%m-%d')})")
                    await download_message_media(client, message, channel_folder)
                    downloaded_count += 1
    except Exception as e:
        print(f"\nAn error occurred during the scan: {e}")
    finally:
        print(f"\nScan complete. A total of {downloaded_count} media files were downloaded.")

def reset_configuration():
    print("\n--- Reset API Configuration ---")
    session_file_to_delete = f"{SESSION_PATH}.session"
    confirm = input(f"This action will delete '{CONFIG_FILE}' and '{session_file_to_delete}'. Are you sure? (y/n): ").lower().strip()
    if confirm == 'y':
        try:
            if os.path.exists(CONFIG_FILE):
                os.remove(CONFIG_FILE)
                print(f"'{CONFIG_FILE}' was successfully deleted.")
            else:
                print(f"'{CONFIG_FILE}' does not exist.")

            if os.path.exists(session_file_to_delete):
                os.remove(session_file_to_delete)
                print(f"'{session_file_to_delete}' was successfully deleted.")
            else:
                 print(f"'{session_file_to_delete}' does not exist.")
            
            print("\nConfiguration has been successfully reset. You can enter the new information when you restart the program.")
        except OSError as e:
            print(f"An error occurred while deleting files: {e}")
    else:
        print("Operation cancelled.")

async def download_menu(client):
    github_url = "https://github.com/MetaSister/Simple-Telegram-DL"
    print(f"GitHub: \033]8;;{github_url}\a{github_url}\033]8;;\a")

    while True:
        print("\n" + "="*50)
        print(" Simple Telegram DL ".center(50, "="))
        print("="*50)
        print("[1] Download from a Single Link or Batch (.txt) File")
        print("[2] Download All Media from a Channel/Chat")
        print("[q] Disconnect and Return to Main Menu")
        choice = input("Please select an option: ").lower().strip()
        
        if choice == '1': await handle_link_download(client)
        elif choice == '2': await handle_channel_download(client)
        elif choice == 'q': break
        else: print("Invalid option, please try again.")

async def main():
    while True:
        try:
            print("\n" + "="*50)
            print(" Main Menu ".center(50, "="))
            print("="*50)
            print("[1] Connect to Telegram and Start Downloading")
            print("[2] Reset API Configuration")
            print("[q] Exit Program")
            main_choice = input("Please select an option: ").lower().strip()

            if main_choice == '1':
                api_id_str, api_hash, from_file = load_or_request_config()

                if not api_id_str or not api_hash:
                    print("\nCould not load API details. Returning to main menu.")
                    continue

                if not os.path.exists(DOWNLOAD_FOLDER): os.makedirs(DOWNLOAD_FOLDER)
                
                client = TelegramClient(SESSION_PATH, api_id_str, api_hash)
                
                try:
                    print("\nConnecting to Telegram...")
                    await client.start(
                        phone=get_validated_phone,
                        password=lambda: getpass("Enter your two-step verification password (or press Enter if none): "),
                        code_callback=lambda: input('Enter the code you received from Telegram: ')
                    )
                    print("Successfully connected!")

                    if not from_file:
                        try:
                            config = configparser.ConfigParser()
                            config['telegram'] = {'api_id': api_id_str, 'api_hash': api_hash}
                            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                                config.write(f)
                            print(f"API details saved to '{CONFIG_FILE}' for future use.")
                        except IOError as e:
                            print(f"\nWARNING: Could not save config file: {e}")

                    await download_menu(client)
                    
                except Exception as e:
                    print(f"\nERROR: Could not connect. Details: {e}")
                    print("\nPlease double-check your API details, phone number, and password.")
                    print("If you just entered new API details, they are likely incorrect.")
                    print(f"If the problem persists, try resetting the configuration using option [2] in the main menu.")
                finally:
                    if client.is_connected():
                        await client.disconnect()
                        print("\nSession terminated. Returning to the main menu.")

            elif main_choice == '2':
                reset_configuration()
            
            elif main_choice == 'q':
                break
            
            else:
                print("Invalid option, please try again.")
        except KeyboardInterrupt:
            break

    print("\nExiting program...")

if __name__ == "__main__":
    if os.name == 'nt': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
