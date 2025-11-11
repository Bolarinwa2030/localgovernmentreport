from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from functools import wraps
from datetime import datetime, timedelta
import secrets
from models import (init_db, User, Complaint, Response, UserRole, 
                    ComplaintStatus, ComplaintPriority, create_admin_user)

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)

# Initialize database
db_session, engine = init_db()
create_admin_user(db_session)

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        user = db_session.query(User).get(session['user_id'])
        if not user or user.role not in [UserRole.ADMIN, UserRole.STAFF]:
            flash('Access denied. Admin privileges required.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            # Check if user exists
            existing_user = db_session.query(User).filter(
                (User.email == request.form['email']) | 
                (User.username == request.form['username'])
            ).first()
            
            if existing_user:
                flash('Email or username already exists!', 'error')
                return redirect(url_for('register'))
            
            # Create new user
            user = User(
                email=request.form['email'],
                username=request.form['username'],
                full_name=request.form['full_name'],
                phone=request.form.get('phone', ''),
                address=request.form.get('address', ''),
                role=UserRole.CITIZEN
            )
            user.set_password(request.form['password'])
            
            db_session.add(user)
            db_session.commit()
            
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            db_session.rollback()
            flash(f'Registration failed: {str(e)}', 'error')
            return redirect(url_for('register'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = db_session.query(User).filter_by(username=username).first()
        
        if user and user.check_password(password) and user.is_active:
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role.value
            session.permanent = True
            
            flash(f'Welcome back, {user.full_name}!', 'success')
            
            if user.role in [UserRole.ADMIN, UserRole.STAFF]:
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('user_dashboard'))
        else:
            flash('Invalid credentials or inactive account!', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def user_dashboard():
    user = db_session.query(User).get(session['user_id'])
    complaints = db_session.query(Complaint).filter_by(user_id=user.id).order_by(
        Complaint.created_at.desc()
    ).all()
    
    stats = {
        'total': len(complaints),
        'pending': len([c for c in complaints if c.status == ComplaintStatus.PENDING]),
        'in_progress': len([c for c in complaints if c.status == ComplaintStatus.IN_PROGRESS]),
        'resolved': len([c for c in complaints if c.status == ComplaintStatus.RESOLVED])
    }
    
    return render_template('user_dashboard.html', user=user, complaints=complaints, stats=stats)

@app.route('/admin')
@admin_required
def admin_dashboard():
    user = db_session.query(User).get(session['user_id'])
    
    # Statistics
    total_complaints = db_session.query(Complaint).count()
    pending_complaints = db_session.query(Complaint).filter_by(status=ComplaintStatus.PENDING).count()
    escalated_complaints = db_session.query(Complaint).filter_by(status=ComplaintStatus.ESCALATED).count()
    total_users = db_session.query(User).filter_by(role=UserRole.CITIZEN).count()
    
    # Recent complaints
    recent_complaints = db_session.query(Complaint).order_by(
        Complaint.created_at.desc()
    ).limit(10).all()
    
    stats = {
        'total': total_complaints,
        'pending': pending_complaints,
        'escalated': escalated_complaints,
        'users': total_users
    }
    
    return render_template('admin_dashboard.html', user=user, stats=stats, 
                         complaints=recent_complaints)

@app.route('/complaint/new', methods=['GET', 'POST'])
@login_required
def new_complaint():
    if request.method == 'POST':
        try:
            # Generate unique ticket number
            ticket_number = f"COMP-{datetime.utcnow().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"
            
            complaint = Complaint(
                ticket_number=ticket_number,
                user_id=session['user_id'],
                title=request.form['title'],
                description=request.form['description'],
                category=request.form['category'],
                location=request.form.get('location', ''),
                priority=ComplaintPriority[request.form.get('priority', 'MEDIUM')]
            )
            
            db_session.add(complaint)
            db_session.commit()
            
            flash(f'Complaint submitted successfully! Ticket: {ticket_number}', 'success')
            return redirect(url_for('user_dashboard'))
            
        except Exception as e:
            db_session.rollback()
            flash(f'Failed to submit complaint: {str(e)}', 'error')
    
    categories = ['Roads & Infrastructure', 'Water Supply', 'Sanitation', 'Electricity', 
                 'Public Safety', 'Healthcare', 'Education', 'Others']
    
    return render_template('new_complaint.html', categories=categories)

@app.route('/complaint/<int:complaint_id>')
@login_required
def view_complaint(complaint_id):
    complaint = db_session.query(Complaint).get(complaint_id)
    
    if not complaint:
        flash('Complaint not found!', 'error')
        return redirect(url_for('user_dashboard'))
    
    user = db_session.query(User).get(session['user_id'])
    
    # Check access rights
    if user.role == UserRole.CITIZEN and complaint.user_id != user.id:
        flash('Access denied!', 'error')
        return redirect(url_for('user_dashboard'))
    
    responses = db_session.query(Response).filter_by(complaint_id=complaint_id)
    if user.role == UserRole.CITIZEN:
        responses = responses.filter_by(is_internal=0)
    responses = responses.order_by(Response.created_at.asc()).all()
    
    return render_template('view_complaint.html', complaint=complaint, responses=responses)

@app.route('/complaint/<int:complaint_id>/update', methods=['POST'])
@admin_required
def update_complaint(complaint_id):
    complaint = db_session.query(Complaint).get(complaint_id)
    
    if not complaint:
        return jsonify({'error': 'Complaint not found'}), 404
    
    try:
        if 'status' in request.form:
            new_status = ComplaintStatus[request.form['status']]
            complaint.status = new_status
            
            if new_status == ComplaintStatus.RESOLVED:
                complaint.resolved_at = datetime.utcnow()
        
        if 'priority' in request.form:
            complaint.priority = ComplaintPriority[request.form['priority']]
        
        if 'assigned_to' in request.form and request.form['assigned_to']:
            complaint.assigned_to = int(request.form['assigned_to'])
        
        complaint.updated_at = datetime.utcnow()
        db_session.commit()
        
        flash('Complaint updated successfully!', 'success')
        
    except Exception as e:
        db_session.rollback()
        flash(f'Update failed: {str(e)}', 'error')
    
    return redirect(url_for('view_complaint', complaint_id=complaint_id))

@app.route('/complaint/<int:complaint_id>/respond', methods=['POST'])
@login_required
def respond_to_complaint(complaint_id):
    complaint = db_session.query(Complaint).get(complaint_id)
    user = db_session.query(User).get(session['user_id'])
    
    if not complaint:
        flash('Complaint not found!', 'error')
        return redirect(url_for('user_dashboard'))
    
    try:
        is_internal = 0
        if user.role in [UserRole.ADMIN, UserRole.STAFF]:
            is_internal = 1 if request.form.get('internal') == 'on' else 0
        
        response = Response(
            complaint_id=complaint_id,
            responder_id=session['user_id'],
            message=request.form['message'],
            is_internal=is_internal
        )
        
        db_session.add(response)
        db_session.commit()
        
        flash('Response added successfully!', 'success')
        
    except Exception as e:
        db_session.rollback()
        flash(f'Failed to add response: {str(e)}', 'error')
    
    return redirect(url_for('view_complaint', complaint_id=complaint_id))

@app.route('/complaint/<int:complaint_id>/escalate', methods=['POST'])
@admin_required
def escalate_complaint(complaint_id):
    complaint = db_session.query(Complaint).get(complaint_id)
    
    if complaint:
        complaint.status = ComplaintStatus.ESCALATED
        complaint.escalation_count += 1
        complaint.priority = ComplaintPriority.HIGH
        complaint.updated_at = datetime.utcnow()
        
        db_session.commit()
        flash('Complaint escalated successfully!', 'success')
    
    return redirect(url_for('view_complaint', complaint_id=complaint_id))

@app.route('/admin/users')
@admin_required
def manage_users():
    users = db_session.query(User).order_by(User.created_at.desc()).all()
    return render_template('manage_users.html', users=users)

@app.route('/admin/reports')
@admin_required
def reports():
    # Generate various statistics
    total_complaints = db_session.query(Complaint).count()
    
    status_counts = {}
    for status in ComplaintStatus:
        count = db_session.query(Complaint).filter_by(status=status).count()
        status_counts[status.value] = count
    
    category_counts = db_session.query(
        Complaint.category, 
    ).group_by(Complaint.category).all()
    
    return render_template('reports.html', 
                         total=total_complaints,
                         status_counts=status_counts,
                         category_counts=category_counts)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)