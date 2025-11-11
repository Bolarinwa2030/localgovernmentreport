from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from werkzeug.security import generate_password_hash, check_password_hash
import enum

Base = declarative_base()

class UserRole(enum.Enum):
    CITIZEN = "citizen"
    ADMIN = "admin"
    STAFF = "staff"

class ComplaintStatus(enum.Enum):
    PENDING = "pending"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CLOSED = "closed"

class ComplaintPriority(enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    email = Column(String(120), unique=True, nullable=False)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(120), nullable=False)
    phone = Column(String(20))
    address = Column(Text)
    role = Column(Enum(UserRole), default=UserRole.CITIZEN)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Integer, default=1)
    
    complaints = relationship('Complaint', back_populates='user', foreign_keys='Complaint.user_id')
    assigned_complaints = relationship('Complaint', back_populates='assigned_to_user', foreign_keys='Complaint.assigned_to')
    responses = relationship('Response', back_populates='responder')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Complaint(Base):
    __tablename__ = 'complaints'
    
    id = Column(Integer, primary_key=True)
    ticket_number = Column(String(50), unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(100), nullable=False)
    location = Column(String(200))
    status = Column(Enum(ComplaintStatus), default=ComplaintStatus.PENDING)
    priority = Column(Enum(ComplaintPriority), default=ComplaintPriority.MEDIUM)
    assigned_to = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    escalation_count = Column(Integer, default=0)
    
    user = relationship('User', back_populates='complaints', foreign_keys=[user_id])
    assigned_to_user = relationship('User', back_populates='assigned_complaints', foreign_keys=[assigned_to])
    responses = relationship('Response', back_populates='complaint', cascade='all, delete-orphan')

class Response(Base):
    __tablename__ = 'responses'
    
    id = Column(Integer, primary_key=True)
    complaint_id = Column(Integer, ForeignKey('complaints.id'), nullable=False)
    responder_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    message = Column(Text, nullable=False)
    is_internal = Column(Integer, default=0)  # Internal notes vs public responses
    created_at = Column(DateTime, default=datetime.utcnow)
    
    complaint = relationship('Complaint', back_populates='responses')
    responder = relationship('User', back_populates='responses')

# Database initialization
def init_db(database_url='sqlite:///complaints.db'):
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session(), engine

def create_admin_user(session):
    """Create default admin user if not exists"""
    admin = session.query(User).filter_by(username='admin').first()
    if not admin:
        admin = User(
            email='admin@localgov.com',
            username='admin',
            full_name='System Administrator',
            role=UserRole.ADMIN,
            phone='0000000000'
        )
        admin.set_password('admin123')
        session.add(admin)
        session.commit()
        print("Admin user created: username='admin', password='admin123'")
    return admin