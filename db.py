import sqlite3
import json
from collections import Counter
from utility import is_running_in_container

data_path = 'data/' if is_running_in_container() else ''

############# DATABASE###################


def startup_db_configurations():
    conn = sqlite3.connect('settings.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            immich_server_url text,
            api_key text,
            images_folder text,
            timeout number
        )
    ''')

    # Check if the table is empty
    c.execute('SELECT COUNT(*) FROM settings')
    if c.fetchone()[0] == 0:
        # Insert default settings, setting timeout to 1500 ms
        c.execute('''
            INSERT INTO settings (immich_server_url, api_key, images_folder, timeout)
            VALUES (?, ?, ?, ?)
        ''', ('', '', '', 2000))

    # Commit changes and close the connection
    conn.commit()
    conn.close()


def load_settings_from_db():
    conn = sqlite3.connect('settings.db')
    c = conn.cursor()
    c.execute("SELECT * FROM settings LIMIT 1")
    settings = c.fetchone()
    conn.close()
    return settings if settings else (None, None, None, None)


def save_settings_to_db(immich_server_url, api_key, images_folder, timeout):
    conn = sqlite3.connect('settings.db')
    c = conn.cursor()
    # This simple logic assumes one row of settings; adjust according to your needs
    c.execute("DELETE FROM settings")  # Clear existing settings
    c.execute("INSERT INTO settings VALUES (?, ?, ?, ?)",
              (immich_server_url, api_key, images_folder, timeout))
    conn.commit()
    conn.close()


def bytes_to_megabytes(bytes_size):
    """Convert bytes to megabytes (MB) and format to 3 decimal places."""
    if bytes_size is None:
        return "0.001 MB"  # Assuming you want to return this default value for None input
    megabytes = bytes_size / (1024 * 1024)
    return f"{megabytes:.3f} MB"


####################### FAISS #############################
def startup_processed_duplicate_faiss_db():
    try:
        conn = sqlite3.connect(data_path + 'duplicates.db')
        cursor = conn.cursor()
        sql = '''CREATE TABLE IF NOT EXISTS duplicates(
           id INTEGER PRIMARY KEY,
           vector_id1 INT,
           vector_id2 INT,
           similarity FLOAT
        )'''
        cursor.execute(sql)
        conn.commit()
    except Exception as e:
        print("Error creating database/table:", e)
    finally:
        conn.close()


def save_duplicate_pair(vector_id1, vector_id2, similarity):
    similarity = float(similarity)
    try:
        conn = sqlite3.connect(data_path + 'duplicates.db')
        cursor = conn.cursor()

        # Check if the pair already exists in either order
        cursor.execute("SELECT * FROM duplicates WHERE (vector_id1 = ? AND vector_id2 = ?) OR (vector_id1 = ? AND vector_id2 = ?)",
                       (vector_id1, vector_id2, vector_id2, vector_id1))
        if cursor.fetchone():
            # print("Duplicate pair already exists.")
            return

        # If not, insert the new pair
        cursor.execute("INSERT INTO duplicates (vector_id1, vector_id2, similarity) VALUES (?, ?, ?)",
                       (vector_id1, vector_id2, similarity))
        conn.commit()
    except Exception as e:
        print("Error inserting duplicate pair:", e)
    finally:
        conn.close()


def delete_duplicate_pair(asset_id_1, asset_id_2):
    try:
        conn = sqlite3.connect(data_path + 'duplicates.db')
        cursor = conn.cursor()
        # Delete the specific duplicate entry involving the two asset IDs
        cursor.execute("DELETE FROM duplicates WHERE (vector_id1 = ? AND vector_id2 = ?) OR (vector_id1 = ? AND vector_id2 = ?)",
                       (asset_id_1, asset_id_2, asset_id_2, asset_id_1))
        conn.commit()
        print("Deleted asset from db")
    except Exception as e:
        print(
            f"Error deleting duplicate entries for asset pair {asset_id_1}-{asset_id_2}:", e)
    finally:
        conn.close()


def load_duplicate_pairs(min_threshold, max_threshold):
    """Load duplicate pairs with a similarity between the specified minimum and maximum thresholds."""
    try:
        conn = sqlite3.connect(data_path + 'duplicates.db')
        cursor = conn.cursor()
        # Adjust the SQL query to filter duplicates within the specified range
        cursor.execute("""
            SELECT vector_id1, vector_id2 FROM duplicates
            WHERE similarity >= ? AND similarity <= ?""",
                       (min_threshold, max_threshold))
        duplicates = cursor.fetchall()
        if not duplicates:
            print(
                f"No duplicates found within thresholds {min_threshold} and {max_threshold}")
        return duplicates
    except Exception as e:
        print("Error loading duplicates:", e)
    finally:
        if conn:
            conn.close()


def is_db_populated():
    """Check if the 'duplicates' table in the database has any entries."""
    conn = None
    try:
        conn = sqlite3.connect(data_path + 'duplicates.db')
        cursor = conn.cursor()
        # Check if there are any rows in the table
        cursor.execute("SELECT EXISTS(SELECT 1 FROM duplicates LIMIT 1)")
        exists = cursor.fetchone()[0]
        return exists == 1
    except Exception as e:
        print("Error checking database population:", e)
        return False
    finally:
        if conn:
            conn.close()


def remove_deleted_assets_from_db(deleted_asset_ids):
    """Remove entries from the duplicates table that involve deleted assets."""
    try:
        conn = sqlite3.connect('duplicates.db')
        cursor = conn.cursor()
        # Prepare placeholders for SQL IN clause
        placeholders = ', '.join('?' for _ in deleted_asset_ids)
        # Since we have two IN clauses, we need to supply the parameters twice
        query = f'''
            DELETE FROM duplicates
            WHERE vector_id1 IN ({placeholders}) OR vector_id2 IN ({placeholders})
        '''
        # Execute the query with the deleted_asset_ids repeated for both placeholders
        params = deleted_asset_ids + deleted_asset_ids  # Concatenate the list with itself
        cursor.execute(query, params)
        conn.commit()
    except Exception as e:
        print("Error removing deleted assets from duplicates db:", e)
    finally:
        conn.close()
