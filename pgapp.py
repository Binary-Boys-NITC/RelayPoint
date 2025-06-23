import hmac
import hashlib
import dotenv,os
import random
import base64
import datetime
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from PIL import Image as PILImage
import io
import json
from datetime import datetime

def binary_to_base64(binary_data, mime_type):
    # Encode binary data to Base64
    base64_data = base64.b64encode(binary_data).decode('utf-8')
    
    # Format as a Data URI
    data_uri = f"data:{mime_type};base64,{base64_data}"
    return data_uri


dotenv.load_dotenv()
database_url=os.getenv("DB_URL")
hash_key=os.getenv("HASH_KEY")
admin_username=os.getenv("ADMIN_USERNAME")
admin_password=os.getenv("ADMIN_PASSWORD")
admin_email=os.getenv("ADMIN_EMAIL")

def hasher(password: str) -> str:
    """
    Hashes a password using HMAC with a provided key (without salting).
    
    Args:
        password (str): The plain text password.
        
    Returns:
        str: The hashed password as a hexadecimal string.
    """
    
    password_bytes = password.encode('utf-8')
    key_bytes = hash_key.encode('utf-8')
    hash_object = hmac.new(key_bytes, password_bytes, hashlib.sha256)
    return hash_object.hexdigest()


from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Table, ARRAY, JSON, LargeBinary
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    username = Column(String, primary_key=True)
    hashed_password = Column(String)
    roles = Column(MutableList.as_mutable(ARRAY(String)))
    secret_key = Column(String, nullable=True)
    email = Column(String, nullable=True)
class UserStats(Base):
    __tablename__ = 'user_stats'
    username = Column(String, ForeignKey('users.username'), primary_key=True)
    events_ids = Column(MutableList.as_mutable(ARRAY(Integer)))
    created_events_ids =  Column(MutableList.as_mutable(ARRAY(Integer)))
    points = Column(MutableList.as_mutable(ARRAY(JSON)), nullable=True)

class Event(Base):
    __tablename__ = 'events'
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, unique=True)
    description = Column(String)
    category = Column(String)
    date = Column(DateTime)
    image_ids = Column(MutableList.as_mutable(ARRAY(Integer)))
    organizers = Column(ARRAY(String))
    access = Column(ARRAY(String))
    registered_users = Column(MutableList.as_mutable(ARRAY(String))) 
    registration_link = Column(String)

class Image(Base):
    __tablename__ = 'images'
    id = Column(Integer, primary_key=True, autoincrement=True)
    data = Column(LargeBinary)
    mime_type = Column(String)

class Post(Base):
    __tablename__ = 'posts'
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, ForeignKey('users.username'))
    blog = Column(String)
    date = Column(DateTime)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(database_url)
Session = sessionmaker(bind=engine)
session = Session()


def pgCreateUser(username:str,password:str,roles:list,email:str):
    user = session.query(User).filter(User.username == username).first()
    if user is None:
        user = session.query(User).filter(User.email == email).first()
        if user is None:
            user = User(username=username, hashed_password=hasher(password), roles=roles,email=email)
            session.add(user)
            user_stats = UserStats(username=username, events_ids=[], created_events_ids=[], points=[])
            session.add(user_stats)
            session.commit()
            return {"status_code":200,"message":"Ok"}
        else:
            return {"status_code":409,"message":f"Email \'{email}\' already exists."}
    else:
        return {"status_code":409,"message":f"Username \'{username}\' already exists."}


def pgLogin(username:str,password:str):
    user = session.query(User).filter(User.username == username).first()
    if user is not None:
        if user.hashed_password == hasher(password):
            secret_key = hasher(hash_key+str(random.randint(1,100000000)))
            user.secret_key = secret_key
            session.commit()
            return {"status_code":200, "message":"Ok", "secret_key":secret_key}
        else:
            return {"status_code":401, "message":"Incorrect credentials"}
    else:
        return {"status_code":404, "message":"User not found"}
    
def pgLogout(username:str,secret_key:str):
    user = session.query(User).filter(User.username == username).first()
    if user is not None:
        if user.secret_key == secret_key:
            user.secret_key = None
            session.commit()
            return {"status_code":200,"message":"Ok"}
        else:
            return {"status_code":404,"message":"Forbidden"}
    else:
        return {"status_code":404,"message":"User not found"}
        
    
def pgUserFetch(username:str):
    user = session.query(User).filter(User.username == username).first()
    if user is not None:
        return {"status_code":200,"message":"Ok","data":{"username":username,"roles":user.roles,"email":user.email}}
    else:
        return {"status_code":404,"message":"User not found"}

def pgUserAddEvents(username:str,secret_key:str,events):
    user = session.query(User).filter(User.username == username).first()
    if user is not None:
        if user.secret_key == secret_key:
            user_stats = session.query(UserStats).filter(UserStats.username == username).first()
            existing_events = user_stats.events_ids
            for id in events:
                    if id not in existing_events:
                        user_stats.events_ids.append(id)
            session.commit()
            return {"status_code":200,"message":"Ok"}
        else:
            return {"status_code":404,"message":"Forbidden"}
    else:
        return {"status_code":404,"message":"User not found"}

def pgUserAuth(username,secret_key):
    user = session.query(User).filter(User.username == username).first()
    if user is not None:
        if user.secret_key == secret_key:
            return True
    return False

def pgAuthorizeCreateEvent(username,secret_key):
    user = session.query(User).filter(User.username == username).first()
    if user is not None:
        if user.secret_key == secret_key:
            if "admin" in user.roles or "organizer" in user.roles:
                return True
    return False
  
def pgCreateEvent(username,title,description,category,date,imageIds=[],organizers=[],access=["all"],registration_link=None):
    date = datetime.datetime(
        year=date["year"],
        month=date["month"],
        day=date["day"],
        hour=date["hour"],
        minute=date["minute"]
    )
    event = session.query(Event).filter(Event.title == title).first()
    if event is not None:
        return {"status_code":409,"message":f"Event \'{title}\' already exists."}
    else:
        event = Event(title=title,description=description,category=category,date=date,image_ids=imageIds,organizers=organizers,access=access,registered_users=[],registration_link=registration_link)
        session.add(event)
        session.commit()
        eventid = event.id
        user_stats = session.query(UserStats).filter(UserStats.username == username).first()
        user_stats.created_events_ids.append(eventid)
        session.commit()
        print(user_stats.created_events_ids)
        return {"status_code":200,"message":"Ok","data":{"id":eventid}}
    
def pgRegisterEvent(username,secret_key,eventid):
    user = session.query(User).filter(User.username == username).first()
    if user is not None:
        event = session.query(Event).filter(Event.id == eventid).first()
        registered_users=event.registered_users
        if username  in registered_users:
            return {"status_code":409,"message":f"Event \'{eventid}\' already registered."}
        else:
            event.registered_users.append(username)
            user_stats = session.query(UserStats).filter(UserStats.username == username).first()
            user_stats.events_ids.append(eventid)
            session.commit()
            return {"status_code":200,"message":"Ok"}
    else:
        return {"status_code":404,"message":"Forbidden"}

def pgNonAwardedUsers(eventId):
    event=session.query(Event).filter(Event.id==eventId).first()
    registered_users=event.registered_users
    user_stats=session.query(UserStats)
    non_awarded_users=[]
    for user in registered_users:
        points=user_stats.filter(UserStats.username==user).first().points
        for point in points:
            if point["event_id"]==eventId:
                break
        else:
            non_awarded_users.append(user)

    return non_awarded_users


def pgAwardPoints(organizerUsername,secret_key,studentUsername,eventId,points):
    user = session.query(User).filter(User.username == organizerUsername).first()
    if user is not None:
        if user.secret_key == secret_key:
            roles=pgUserFetch(organizerUsername)["data"]["roles"]

            if "organizer" in roles or "admin" in roles:
                event = session.query(Event).filter(Event.id == eventId).first()
                organizers=event.organizers
                if organizerUsername in organizers or "admin" in roles:
                    user_stats = session.query(UserStats).filter(UserStats.username == studentUsername).first()
                    if user_stats is not None:
                        for point in user_stats.points:
                            if point["event_id"]==eventId:
                                break
                        else:
                            user_stats.points.append({"event_id":int(eventId),"points":int(points)})
                            session.commit()
                            return {"status_code":200,"message":"Ok"}
                    else:
                        return {"status_code":404,"message":"User not found"}
                else:
                    return {"status_code":404,"message":"Event not Organized by User"}
            else:
                return {"status_code":404,"message":"User not an Organizer"}
    else:
        return {"status_code":404,"message":"Forbidden"}

def pgAwardAllPoints(organizerUsername,secret_key,eventId,points):
    user = session.query(User).filter(User.username == organizerUsername).first()
    if user is not None:
        if user.secret_key == secret_key:
            roles=pgUserFetch(organizerUsername)["data"]["roles"]

            if "organizer" in roles or "admin" in roles:
                non_awarded_users=pgNonAwardedUsers(eventId)
                for user in non_awarded_users:
                    user_stats = session.query(UserStats).filter(UserStats.username == user).first()
                    if user_stats is not None:
                        for point in user_stats.points:
                            if point["event_id"]==eventId:
                                break
                        else:
                            user_stats.points.append({"event_id":int(eventId),"points":int(points)})
                            session.commit()
                else:
                    return {"status_code":200,"message":"Ok"}
            else:
                return {"status_code":404,"message":"Event not Organized by User"}
        else:
            return {"status_code":404,"message":"Forbidden"}
    else:
        return {"status_code":404,"message":"Forbidden"}

def pgAddOrganizers(creatorUsername,secret_key,eventId,organizers:list):
    user = session.query(User).filter(User.username == creatorUsername).first()
    if user is not None:
        if user.secret_key == secret_key:
            user_stats = session.query(UserStats).filter(UserStats.username == creatorUsername).first()
            if eventId in user_stats.created_events_ids:
                event = session.query(Event).filter(Event.id == eventId).first()
                event.organizers.extend(organizers)
                session.commit()
                return {"status_code":200,"message":"Ok"}
            else:
                return {"status_code":404,"message":"Only Creators can add organizers"}
        else:
            return {"status_code":404,"message":"Forbidden"}
    else:
        return {"status_code":404,"message":"Forbidden"}

def pointsTotal(points):
    sum=0
    for event in points:
        sum+=event["points"]
    return sum

def pgRanklist():
    users=session.query(UserStats).all()
    return sorted(users,key=lambda i:pointsTotal(i.points),reverse=True)

def pgGetRank(username:str):
    RL=pgRanklist()
    for i in range(len(RL)):
        if RL[i].username==username:
            return i+1

def pgGetRecentEvents(username,secret_key):
    user = session.query(User).filter(User.username == username).first()
    if user is not None:
        if user.secret_key == secret_key:
            user_stats = session.query(UserStats).filter(UserStats.username == username).first()
            events=user_stats.events_ids
            return events[::-1]
        else:
            return False
    else:
        return False

def pgGetCreatedEvents(username,secret_key):
    user = session.query(User).filter(User.username == username).first()
    if user is not None:
        if user.secret_key == secret_key:
            user_stats = session.query(UserStats).filter(UserStats.username == username).first()
            
            events=user_stats.created_events_ids
            return events[::-1]
        else:
            return False
    else:
        return False


def pgGetEvent(id:int):
    """
        Returns Event object
    """
    event = session.query(Event).filter(Event.id == id).first()
    return event

def pgUploadImage(image):
    img = PILImage.open(image.stream)
    
    if img.mode in ('RGBA', 'LA', 'P'):
        img = img.convert('RGB')
    
    max_size = (1200, 800)
    img.thumbnail(max_size, PILImage.Resampling.LANCZOS)
    
    output = io.BytesIO()
    img.save(output, format='JPEG', quality=85, optimize=True) 
    binary_data = output.getvalue()
    
    mimetype = 'image/jpeg'
    
    image = Image(data=binary_data,mime_type=mimetype)
    session.add(image)
    session.commit()
    return image.id

def pgGetImage(id:int):
    image = session.query(Image).filter(Image.id == id).first()
    return binary_to_base64(image.data,image.mime_type)

def pgGetPoints(username):
    user_stats = session.query(UserStats).filter(UserStats.username == username).first()
    points=0
    for i in user_stats.points:
        points+=i["points"]
    return points

def pgPostBlog(username,secret_key,blog,time):
    user = session.query(User).filter(User.username == username).first()
    if user is not None:
        if user.secret_key == secret_key:
            session.add(Post(username=username,blog=blog,date=time))
            session.commit()
            return {"status_code":200,"message":"Ok"}
        else:
            return {"status_code":404,"message":"Forbidden"}
    else:
        return {"status_code":404,"message":"User not found"}

def pgGetBlogs():
    posts=session.query(Post).all()
    return posts[::-1]

def pgAppStats():
    events=session.query(Event).all()
    number_of_hackathons=0
    number_of_tickets=0
    for event in events:
        if event.category=="Hackathon":
            number_of_hackathons+=1
        number_of_tickets+=len(event.registered_users)
    return {"events":len(events),"hackathons":number_of_hackathons,"tickets":number_of_tickets}

def pgGetParticipants(eventId:int):
    event=session.query(Event).filter(Event.id==eventId).first()
    registered_users=event.registered_users
    users={"participants":[]}
    for user in registered_users:
        user_data=session.query(User).filter(User.username==user).first()
        users["participants"].append({"username":user_data.username,"email":user_data.email})
    return users

def pgMakeOrganizer(organizer,username,secret_key):
    user = session.query(User).filter(User.username == username).first()
    if user is not None:
        if user.secret_key == secret_key and "admin" in user.roles:
            organizer = session.query(User).filter(User.username == organizer).first()
            if organizer is not None:
                if "organizer" not in organizer.roles:
                    organizer.roles.append("organizer")
                    session.commit()
                    return {"status_code":200,"message":"Ok"}
                else:
                    return {"status_code":409,"message":"User already an organizer"}
            else:
                return {"status_code":404,"message":"User not found"}
        else:
            return {"status_code":404,"message":"Forbidden"}
    else:
        return {"status_code":404,"message":"User not found"}

def resetdb():
    global session
    session.close()
    """
    Drops all tables and recreates them from the defined SQLAlchemy models.
    WARNING: This will erase all existing data!
    """
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    print("Database has been reset.")

    session = Session()

def pgAdminResetDB(username,secret_key):
    """
    Safer version that handles session lifecycle properly.
    """
    try:
        # Create a temporary session for verification
        temp_session = Session()
        
        # Verify admin privileges
        user = temp_session.query(User).filter(User.username == username).first()
        if user is None:
            temp_session.close()
            return {"status_code": 404, "message": "User not found"}
        
        if user.secret_key != secret_key or "admin" not in user.roles:
            temp_session.close()
            return {"status_code": 403, "message": "Forbidden"}
        
        # Close the temp session
        temp_session.close()
        
        # Close the global session
        session.close()
        
        # Reset database
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        
        # Create new session for admin user creation
        reset_session = Session()
        
        try:
            # Create admin user
            admin_user = User(
                username=admin_username,
                hashed_password=hasher(admin_password),
                roles=["admin"],
                email=admin_email
            )
            reset_session.add(admin_user)
            
            # Create admin stats
            admin_stats = UserStats(
                username=admin_username,
                events_ids=[],
                created_events_ids=[],
                points=[]
            )
            reset_session.add(admin_stats)
            
            reset_session.commit()
            
            return {"status_code": 200, "message": "Database reset successfully"}
            
        except Exception as e:
            reset_session.rollback()
            raise e
        finally:
            reset_session.close()
            
    except Exception as e:
        print(f"Error during safe database reset: {e}")
        return {"status_code": 500, "message": f"Database reset failed: {str(e)}"}

def reinitialize_session():
    """
    Reinitialize the global session after database operations.
    Call this after resetdb if you need to continue using the global session.
    """
    global session
    try:
        session.close()
    except:
        pass  # Session might already be closed
    
    session = Session()
    return session

def export_to_json(session):
    """
    Export database data to JSON format
    Note: Binary data (images) will be base64 encoded
    """
    export_data = {
        'status_code': 200,
        'message': 'Database exported successfully',
        'users': [],
        'user_stats': [],
        'events': [],
        'images': [],
        'posts': [],
        'export_timestamp': datetime.now().isoformat()
    }
    
    # Export Users
    users = session.query(User).all()
    for user in users:
        export_data['users'].append({
            'username': user.username,
            'hashed_password': user.hashed_password,
            'roles': user.roles,
            'secret_key': user.secret_key,
            'email': user.email
        })
    
    # Export UserStats
    user_stats = session.query(UserStats).all()
    for stat in user_stats:
        export_data['user_stats'].append({
            'username': stat.username,
            'events_ids': stat.events_ids,
            'created_events_ids': stat.created_events_ids,
            'points': stat.points
        })
    
    # Export Events
    events = session.query(Event).all()
    for event in events:
        export_data['events'].append({
            'id': event.id,
            'title': event.title,
            'description': event.description,
            'category': event.category,
            'date': event.date.isoformat() if event.date else None,
            'image_ids': event.image_ids,
            'organizers': event.organizers,
            'access': event.access,
            'registered_users': event.registered_users,
            'registration_link': event.registration_link
        })
    
    # Export Images (with base64 encoding)
    images = session.query(Image).all()
    for image in images:
        export_data['images'].append({
            'id': image.id,
            'data': binary_to_base64(image.data, image.mime_type) if image.data else None,
            'mime_type': image.mime_type
        })
    
    # Export Posts
    posts = session.query(Post).all()
    for post in posts:
        export_data['posts'].append({
            'id': post.id,
            'username': post.username,
            'blog': post.blog,
            'date': post.date.isoformat() if post.date else None
        })
    
    return export_data

def import_from_json(import_data, clear_existing=False):
    """
    Import database data from JSON format
    """

    if clear_existing:
        session.close()
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        reset_session = Session()
        
        try:
            # Create admin user
            admin_user = User(
                username=admin_username,
                hashed_password=hasher(admin_password),
                roles=["admin"],
                email=admin_email
            )
            reset_session.add(admin_user)
            
            # Create admin stats
            admin_stats = UserStats(
                username=admin_username,
                events_ids=[],
                created_events_ids=[],
                points=[]
            )
            reset_session.add(admin_stats)
            reset_session.commit()

        except Exception as e:
            reset_session.rollback()
            raise e
        finally:
            reset_session.close()
        reinitialize_session()
    try:
        # Import Users
        for user_data in import_data['users']:
            user = User(
                username=user_data['username'],
                hashed_password=user_data['hashed_password'],
                roles=user_data['roles'],
                secret_key=user_data['secret_key'],
                email=user_data['email']
            )
            session.merge(user)  # Use merge to handle duplicates
        
        # Import UserStats
        for stat_data in import_data['user_stats']:
            stat = UserStats(
                username=stat_data['username'],
                events_ids=stat_data['events_ids'],
                created_events_ids=stat_data['created_events_ids'],
                points=stat_data['points']
            )
            session.merge(stat)
        
        # Import Events
        for event_data in import_data['events']:
            event = Event(
                id=event_data['id'],
                title=event_data['title'],
                description=event_data['description'],
                category=event_data['category'],
                date=datetime.fromisoformat(event_data['date']) if event_data['date'] else None,
                image_ids=event_data['image_ids'],
                organizers=event_data['organizers'],
                access=event_data['access'],
                registered_users=event_data['registered_users'],
                registration_link=event_data['registration_link']
            )
            session.merge(event)
        
        # Import Images
        for image_data in import_data['images']:
            if image_data['data']:
                # Convert base64 back to binary
                data_uri = image_data['data']
                if data_uri.startswith('data:'):
                    base64_data = data_uri.split(',')[1]
                    binary_data = base64.b64decode(base64_data)
                else:
                    binary_data = base64.b64decode(image_data['data'])
            else:
                binary_data = None
                
            image = Image(
                id=image_data['id'],
                data=binary_data,
                mime_type=image_data['mime_type']
            )
            session.merge(image)
        
        # Import Posts
        for post_data in import_data['posts']:
            post = Post(
                id=post_data['id'],
                username=post_data['username'],
                blog=post_data['blog'],
                date=datetime.fromisoformat(post_data['date']) if post_data['date'] else None
            )
            session.merge(post)
        
        session.commit()
        return {"status_code": 200, "message": "Database imported successfully"}
    except Exception as e:
        print(e)
        return {"status_code": 500, "message": f"Error during database import: {e}"}

def pgExportDB(username,secret_key):
    user = session.query(User).filter(User.username == username).first()
    if user is not None:
        if user.secret_key == secret_key and "admin" in user.roles:
            export_data = export_to_json(session)
            return export_data
        else:
            return {"status_code": 403, "message": "Forbidden"}
    else:
        return {"status_code": 404, "message": "User not found"}

def pgImportDB(username,secret_key,import_data,clear_existing=False):
    user = session.query(User).filter(User.username == username).first()
    if user is not None:
        if user.secret_key == secret_key and "admin" in user.roles:
            if import_from_json(import_data,clear_existing)['status_code'] == 200:
                return {"status_code": 200, "message": "Database imported successfully"}
            else:
                return {"status_code": 500, "message": "Error during database import"}
        else:
            return {"status_code": 403, "message": "Forbidden"}
    else:
        return {"status_code": 404, "message": "User not found"}

if __name__ == "__main__":
    resetdb()
    pgCreateUser(admin_username,admin_password,["admin"],admin_email)