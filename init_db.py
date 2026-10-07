import os
import pymysql
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

# Load environment variables
load_dotenv()

DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_USER = os.environ.get('DB_USER', 'root')
DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
DB_NAME = os.environ.get('DB_NAME', 'nepal_travel_db')
DB_PORT = int(os.environ.get('DB_PORT', 3306))

def init_database():
    print(f"Connecting to MySQL server at {DB_HOST}:{DB_PORT} as '{DB_USER}'...")
    try:
        # Step 1: Connect to MySQL server without selecting database
        conn = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT,
            autocommit=True
        )
        cursor = conn.cursor()
        print("Connected to MySQL server successfully!")
        
        # Step 2: Create Database if not exists
        print(f"Creating database '{DB_NAME}' if not exists...")
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        cursor.execute(f"USE `{DB_NAME}`")
        
        # Step 3: Run schema
        schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
        if os.path.exists(schema_path):
            print("Applying schema.sql...")
            with open(schema_path, 'r', encoding='utf-8') as f:
                sql_commands = f.read().split(';')
                for cmd in sql_commands:
                    cmd = cmd.strip()
                    if cmd:
                        cursor.execute(cmd)
            print("Schema applied successfully!")
        else:
            print("schema.sql not found, skipping schema file import.")

        # Step 4: Seed default Admin User if not exists
        cursor.execute("SELECT id FROM users WHERE email = 'admin@example.com'")
        if not cursor.fetchone():
            hashed_admin_pwd = generate_password_hash("admin123")
            cursor.execute(
                "INSERT INTO users (full_name, email, phone, password, role) VALUES (%s, %s, %s, %s, %s)",
                ("Admin User", "admin@example.com", "9800000000", hashed_admin_pwd, "admin")
            )
            print("Created default admin account: admin@example.com / password: admin123")
        
        # Step 5: Seed Sample Destinations if empty
        cursor.execute("SELECT COUNT(*) AS count FROM destinations")
        dest_count = cursor.fetchone()[0]
        if dest_count == 0:
            print("Seeding sample destinations...")
            sample_destinations = [
                (
                    "Pokhara",
                    "Gandaki Province, Nepal",
                    "Pokhara is a city on Phewa Lake, in central Nepal. It is known as the gateway to the Annapurna Circuit.",
                    "pokhara.jpg",
                    "Lakes & Adventure",
                    "Boating, Paragliding, Mountain Views, Caves",
                    "September to November, March to May",
                    "Historically an important trade route between India and Tibet.",
                    28.2096,
                    83.9856
                ),
                (
                    "Chitwan National Park",
                    "Chitwan, Bagmati Province, Nepal",
                    "Chitwan National Park is the first national park of Nepal, famed for biodiversity and wildlife safaris.",
                    "chitwan.jpg",
                    "Wildlife & Safari",
                    "One-horned Rhinos, Bengal Tigers, Elephant Safari, Canoeing",
                    "October to March",
                    "Established in 1973 and declared a UNESCO World Heritage Site in 1984.",
                    27.5341,
                    84.4525
                ),
                (
                    "Everest Base Camp",
                    "Solukhumbu, Koshi Province, Nepal",
                    "The iconic Everest Base Camp trek offers stunning Himalayan panoramas and Sherpa cultural immersion.",
                    "everest.jpg",
                    "Trekking & Mountains",
                    "Panoramic Himalayan views, Sherpa culture, Tengboche Monastery",
                    "March to May, September to November",
                    "First climbed in 1953 by Sir Edmund Hillary and Tenzing Norgay Sherpa.",
                    28.0044,
                    86.8569
                ),
                (
                    "Kathmandu Valley",
                    "Bagmati Province, Nepal",
                    "The cultural heartbeat of Nepal, boasting multiple UNESCO World Heritage durbar squares and stupas.",
                    "kathmandu.jpg",
                    "Culture & Heritage",
                    "Ancient temples, Durbar Squares, Stupas, Living Goddess Kumari",
                    "September to November, February to April",
                    "Ancient Newar kingdom renowned for exquisite arts and crafts architecture.",
                    27.7172,
                    85.3240
                )
            ]
            
            for dest in sample_destinations:
                cursor.execute(
                    """INSERT INTO destinations 
                       (name, location, description, image, category, special_features, best_time_to_visit, history, latitude, longitude)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    dest
                )
            print("Added 4 sample destinations!")
            
            # Seed sample packages
            cursor.execute("SELECT id, name FROM destinations")
            dests = {row[1]: row[0] for row in cursor.fetchall()}
            
            if "Pokhara" in dests:
                cursor.execute(
                    """INSERT INTO packages (destination_id, title, description, price, duration_days, max_people, image)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (dests["Pokhara"], "Pokhara Lake & Adventure 3-Day Tour", "Experience scenic Phewa lake, caves, and mountain sunrises.", 15000.00, 3, 10, "pokhara_pkg.jpg")
                )
                pkg_id = cursor.lastrowid
                cursor.execute(
                    """INSERT INTO package_itineraries (package_id, day_number, title, description, latitude, longitude)
                       VALUES (%s, 1, 'Arrival & Phewa Lake Boating', 'Arrive in Pokhara, evening boating at Phewa Lake.', 28.2096, 83.9856),
                              (%s, 2, 'Sarangkot Sunrise & Sightseeing', 'Watch sunrise over Annapurna, visit Davis Falls & Caves.', 28.2439, 83.9472),
                              (%s, 3, 'Peace Pagoda & Departure', 'Hike up to World Peace Pagoda before departure.', 28.1887, 83.9782)""",
                    (pkg_id, pkg_id, pkg_id)
                )

            if "Chitwan National Park" in dests:
                cursor.execute(
                    """INSERT INTO packages (destination_id, title, description, price, duration_days, max_people, image)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (dests["Chitwan National Park"], "Chitwan Jungle Safari 2-Day Package", "Exciting wildlife jeep safari and canoe ride.", 12000.00, 2, 8, "chitwan_pkg.jpg")
                )
                pkg_id = cursor.lastrowid
                cursor.execute(
                    """INSERT INTO package_itineraries (package_id, day_number, title, description, latitude, longitude)
                       VALUES (%s, 1, 'Jeep Safari & Tharu Cultural Show', 'Jeep ride into deep core jungle, evening cultural dance.', 27.5341, 84.4525),
                              (%s, 2, 'Canoe Ride & Bird Watching', 'Morning canoe trip on Rapti river followed by departure.', 27.5683, 84.4842)""",
                    (pkg_id, pkg_id)
                )

            print("Added sample packages and itineraries!")

        cursor.close()
        conn.close()
        print("\nAll database tables and initial data setup successfully completed!")
        print("You can now run: python app.py")

    except pymysql.err.OperationalError as e:
        code, msg = e.args
        if code == 2003:
            print("\n[ERROR] MySQL Server is NOT running!")
            print("Please start MySQL in XAMPP Control Panel or Windows Services and try again.")
        elif code == 1045:
            print("\n[ERROR] Access denied (wrong MySQL username or password).")
            print("Please check DB_USER and DB_PASSWORD in your .env file.")
        else:
            print(f"\n[ERROR] Database operational error: {e}")
    except Exception as e:
        print(f"\n[ERROR] Failed to initialize database: {e}")

if __name__ == '__main__':
    init_database()
