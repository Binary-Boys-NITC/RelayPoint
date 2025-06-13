import hmac
import hashlib
import dotenv,os
import random
import base64
import datetime
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.mutable import MutableList
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
    roles = Column(ARRAY(String))
    secret_key = Column(String, nullable=True)

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


def pgCreateUser(username:str,password:str,roles:list):
    user = session.query(User).filter(User.username == username).first()
    if user is None:
        user = User(username=username, hashed_password=hasher(password), roles=roles)
        session.add(user)
        user_stats = UserStats(username=username, events_ids=[], created_events_ids=[], points=[])
        session.add(user_stats)
        session.commit()
        return {"status_code":200,"message":"Ok"}
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
        return {"status_code":200,"message":"Ok","data":{"username":username,"roles":user.roles}}
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

def pgAuthorizeCreateEvent(username,secret_key):
    user = session.query(User).filter(User.username == username).first()
    if user is not None:
        if user.secret_key == secret_key:
            if "admin" in user.roles or "organizer" in user.roles:
                return True
    return False
  
def pgCreateEvent(username,title,description,category,date,imageIds=[],organizers=[],access=["all"]):
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
        event = Event(title=title,description=description,category=category,date=date,image_ids=imageIds,organizers=organizers,access=access,registered_users=[])
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
                        if {"event_id":int(eventId),"points":int(points)} not in user_stats.points:
                            user_stats.points.append({"event_id":int(eventId),"points":int(points)})
                            session.commit()
                            return {"status_code":200,"message":"Ok"}
                        else:
                            return {"status_code":409,"message":f"Event \'{eventId}\' already awarded."}
                    else:
                        return {"status_code":404,"message":"User not found"}
                else:
                    return {"status_code":404,"message":"Event not Organized by User"}
            else:
                return {"status_code":404,"message":"User not an Organizer"}
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

def pgUploadImage(data,mime_type):
    image = Image(data=data,mime_type=mime_type)
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

def pgAppStats():
    events=session.query(Event).all()
    number_of_hackathons=0
    number_of_tickets=0
    for event in events:
        if event.category=="Hackathon":
            number_of_hackathons+=1
        number_of_tickets+=len(event.registered_users)
    return {"events":len(events),"hackathons":number_of_hackathons,"tickets":number_of_tickets}

def resetdb():
    """
    Drops all tables and recreates them from the defined SQLAlchemy models.
    WARNING: This will erase all existing data!
    """
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    print("Database has been reset.")

if __name__ == "__main__":
    resetdb()
    pgCreateUser(admin_username,admin_password,["admin"])