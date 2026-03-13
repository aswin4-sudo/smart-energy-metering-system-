from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    is_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(100))
    reset_token = db.Column(db.String(100))
    reset_token_expiry = db.Column(db.DateTime)
    monthly_limit = db.Column(db.Float, default=1000.0)
    alert_threshold = db.Column(db.Float, default=0.8)
    email_notifications = db.Column(db.Boolean, default=True)

    def set_password(self, password, bcrypt_obj):
        self.password_hash = bcrypt_obj.generate_password_hash(password).decode('utf-8')
    
    def check_password(self, password, bcrypt_obj):
        return bcrypt_obj.check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'is_verified': self.is_verified,
            'monthly_limit': self.monthly_limit,
            'is_active': self.is_active,
            'alert_threshold': self.alert_threshold,
            'email_notifications': self.email_notifications
        }

class MCBReading(db.Model):
    __tablename__ = 'mcb_readings'
    timestamp = db.Column(db.DateTime, primary_key=True)
    current_a = db.Column(db.Float)
    voltage_v = db.Column(db.Float)
    power_factor = db.Column(db.Float)
    power_w = db.Column(db.Float)
    energy_kwh = db.Column(db.Float)
    mcb_id = db.Column(db.Integer)  
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    user = db.relationship('User', backref='readings')