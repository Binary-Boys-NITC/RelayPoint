import smtplib
from email.mime.text import MIMEText
import dotenv
import os

dotenv.load_dotenv()

def send_email(recipient_email, subject, message):
    try:
        # Your Gmail credentials
        sender_email = os.getenv("VERIFY_EMAIL")
        sender_password = os.getenv("VERIFY_PASSWORD")
        
        # Create email
        msg = MIMEText(message)
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = recipient_email
        
        # Send email
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
        
        return True
    except Exception as e:
        return False
