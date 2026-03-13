from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from datetime import datetime, timedelta, timezone
import re
import secrets
import string
from functools import wraps
from sqlalchemy import text
from models import db, User
from flask import current_app

def get_bcrypt():
    return current_app.extensions['bcrypt']

auth_bp = Blueprint('auth', __name__)

def get_db():
    from flask import current_app
    return current_app.extensions['sqlalchemy'].db

def get_bcrypt():
    from flask import current_app
    return current_app.extensions['bcrypt']

def get_user_model():
    from app import User
    return User

def generate_token(length=32):
    """Generate a secure random token"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

@auth_bp.route('/api/auth/signup', methods=['POST'])
def signup():
    # Import at the top of the function
    from flask import current_app
    from app import db, bcrypt, User
    
    # Force use of current app context
    with current_app.app_context():
        try:
            current_app.logger.info("🔍 === SIGNUP PROCESS STARTED ===")
            
            data = request.get_json()
            current_app.logger.info(f"📋 Received data: {data}")
            
            if not data:
                return jsonify({"error": "No data received"}), 400
            
            # Validation
            required_fields = ['name', 'email', 'password']
            missing_fields = [field for field in required_fields if field not in data]
            if missing_fields:
                return jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}), 400
            
            email = data['email'].strip().lower()
            name = data['name'].strip()
            password = data['password']
            
            current_app.logger.info(f"👤 Processing: {name} <{email}>")
            
            # Check existing user
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                current_app.logger.warning(f"⚠️ User already exists: {email}")
                return jsonify({"error": "User already exists"}), 400
            
            # Create user
            user = User(
                name=name,
                email=email,
                is_verified=True,
                is_active=True,
                monthly_limit=1000.0,
                alert_threshold=0.8,
                email_notifications=True,
                created_at=datetime.now(timezone.utc)
            )
            
            user.set_password(password, bcrypt)
            current_app.logger.info("✅ Password hash created")
            
            db.session.add(user)
            db.session.flush()
            user_id = user.id
            current_app.logger.info(f"📝 User ID assigned: {user_id}")
            
            db.session.commit()
            current_app.logger.info("✅ Database commit successful")
            
            # Verify
            saved_user = User.query.get(user_id)
            
            if saved_user:
                current_app.logger.info(f"🎉 USER SAVED - ID: {saved_user.id}, Email: {saved_user.email}")
                return jsonify({
                    "message": "Account created successfully",
                    "user": saved_user.to_dict()
                }), 201
            else:
                current_app.logger.error("❌ User not found after commit!")
                db.session.rollback()
                return jsonify({"error": "Database error"}), 500
                    
        except Exception as e:
            current_app.logger.error(f"💥 SIGNUP ERROR: {str(e)}", exc_info=True)
            db.session.rollback()
            return jsonify({"error": f"Signup failed: {str(e)}"}), 500

@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    from app import db, bcrypt, User
    
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        current_app.logger.info(f"🔍 Login attempt for: {email}")
        
        if not email or not password:
            return jsonify({'error': 'Email and password required'}), 400
        
        # Find user
        user = User.query.filter_by(email=email).first()
        
        if not user:
            current_app.logger.warning(f"❌ User not found: {email}")
            return jsonify({'error': 'Invalid credentials'}), 401
            
        if not user.check_password(password, bcrypt):
            current_app.logger.warning(f"❌ Invalid password for: {email}")
            return jsonify({'error': 'Invalid credentials'}), 401
        
        if not user.is_active:
            return jsonify({'error': 'Account deactivated'}), 403
        
        # Update last login with proper transaction
        try:
            user.last_login = datetime.now(timezone.utc)
            db.session.commit()
        except Exception as e:
            current_app.logger.error(f"Failed to update last login: {str(e)}")
            # Continue anyway - login can proceed
        
        # Create JWT token
        access_token = create_access_token(
            identity=str(user.id),
            expires_delta=timedelta(days=7),
            additional_claims={'email': user.email, 'name': user.name}
        )
        
        current_app.logger.info(f"✅ Login successful for: {email}")
        
        return jsonify({
            'token': access_token,
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Login error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Login failed'}), 500

def assign_existing_dataset_to_user(user_id, email):
    """Assign one of the pre-existing datasets to the new user"""
    try:
        from app import db, MCBReading
        
        current_app.logger.info(f"Starting dataset assignment for user {user_id}")
        
        # Check if user already has data
        existing_data = MCBReading.query.filter_by(user_id=user_id).first()
        if existing_data:
            current_app.logger.info(f"User {user_id} already has data")
            return
        
        # Get available datasets
        dataset_users = db.session.query(MCBReading.user_id).distinct().filter(
            MCBReading.user_id.isnot(None),
            MCBReading.user_id != user_id
        ).all()
        dataset_users = [user[0] for user in dataset_users if user[0] is not None]
        
        if not dataset_users:
            current_app.logger.warning("No existing datasets, creating sample data")
            create_sample_data_for_user(user_id)
            return
        
        # Assign dataset based on email hash
        email_hash = hash(email)
        dataset_index = abs(email_hash) % len(dataset_users)
        source_user_id = dataset_users[dataset_index]
        
        current_app.logger.info(f"Copying dataset from user {source_user_id} to {user_id}")
        
        # Copy data in batches
        batch_size = 100
        offset = 0
        total_copied = 0
        
        while True:
            source_data = MCBReading.query.filter_by(user_id=source_user_id)\
                .offset(offset).limit(batch_size).all()
            
            if not source_data:
                break
            
            for reading in source_data:
                new_reading = MCBReading(
                    timestamp=reading.timestamp,
                    current_a=reading.current_a,
                    voltage_v=reading.voltage_v,
                    power_factor=reading.power_factor,
                    power_w=reading.power_w,
                    energy_kwh=reading.energy_kwh,
                    mcb_id=reading.mcb_id,
                    user_id=user_id
                )
                db.session.add(new_reading)
            
            db.session.flush()  # Flush batch
            total_copied += len(source_data)
            offset += batch_size
            
            if total_copied % 500 == 0:  # Commit every 500 records
                db.session.commit()
                current_app.logger.info(f"Committed {total_copied} records")
        
        db.session.commit()  # Final commit
        current_app.logger.info(f"Successfully copied {total_copied} records to user {user_id}")
        
    except Exception as e:
        current_app.logger.error(f"Error assigning dataset: {str(e)}", exc_info=True)
        try:
            db.session.rollback()
            create_sample_data_for_user(user_id)
        except:
            pass

def create_sample_data_for_user(user_id):
    """Create minimal sample data for new users"""
    try:
        from app import db, MCBReading
        from datetime import datetime, timedelta, timezone
        
        current_app.logger.info(f"Creating sample data for user {user_id}")
        
        base_time = datetime.now(timezone.utc) - timedelta(hours=24)
        
        for hour in range(24):
            timestamp = base_time + timedelta(hours=hour)
            reading = MCBReading(
                timestamp=timestamp,
                current_a=10.0 + (hour % 5),
                voltage_v=230.0 + (hour % 3),
                power_factor=0.95,
                power_w=2300.0 + (hour * 50),
                energy_kwh=hour * 2.5,
                mcb_id=1,
                user_id=user_id
            )
            db.session.add(reading)
        
        db.session.flush()  # Flush before commit
        db.session.commit()
        current_app.logger.info(f"Created sample data for user {user_id}")
        
    except Exception as e:
        current_app.logger.error(f"Error creating sample data: {str(e)}")
        db.session.rollback()

@auth_bp.route('/api/auth/logout', methods=['POST'])
@jwt_required()
def logout():
    return jsonify({'message': 'Logged out successfully'}), 200

@auth_bp.route('/api/auth/profile', methods=['GET'])
@jwt_required()
def get_profile():
    try:
        User = get_user_model()
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({'user': user.to_dict()}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@auth_bp.route('/api/auth/profile', methods=['PUT'])
@jwt_required()
def update_profile():
    try:
        db = get_db()
        User = get_user_model()
        
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json()
        
        if 'name' in data:
            user.name = data['name']
        if 'monthly_limit' in data:
            user.monthly_limit = float(data['monthly_limit'])
        if 'alert_threshold' in data:
            user.alert_threshold = float(data['alert_threshold'])
        if 'email_notifications' in data:
            user.email_notifications = bool(data['email_notifications'])
        
        db.session.flush()
        db.session.commit()
        
        return jsonify({
            'message': 'Profile updated successfully',
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@auth_bp.route('/api/auth/change-password', methods=['POST'])
@jwt_required()
def change_password():
    try:
        db = get_db()
        User = get_user_model()
        bcrypt = get_bcrypt()
        
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json()
        old_password = data.get('old_password')
        new_password = data.get('new_password')
        
        if not user.check_password(old_password, bcrypt):
            return jsonify({'error': 'Current password is incorrect'}), 401
        
        if len(new_password) < 6:
            return jsonify({'error': 'New password must be at least 6 characters'}), 400
        
        user.set_password(new_password, bcrypt)
        db.session.flush()
        db.session.commit()
        
        return jsonify({'message': 'Password changed successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
@auth_bp.route('/api/auth/simple-insert-test', methods=['GET'])
def simple_insert_test():
    from app import db, User, bcrypt
    import time
    
    try:
        test_email = f"test_{int(time.time())}@test.com"
        
        current_app.logger.info(f"Creating user: {test_email}")
        
        user = User(
            name="Simple Test",
            email=test_email,
            is_verified=True,
            is_active=True
        )
        user.set_password("test123", bcrypt)
        
        db.session.add(user)
        db.session.commit()
        
        current_app.logger.info("Commit completed")
        
        # Check with raw SQL
        found = db.session.execute(
            text("SELECT id, email FROM users WHERE email = :email"),
            {"email": test_email}
        ).fetchone()
        
        return jsonify({
            "success": True,
            "user_id": user.id,
            "found_in_db": found is not None,
            "email": test_email
        })
        
    except Exception as e:
        current_app.logger.error(f"Error: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
# Test endpoint to verify database connection
@auth_bp.route('/api/auth/test-db', methods=['GET'])
def test_db():
    """Test database connection and user creation"""
    from app import db, User
    
    try:
        # Test 1: Check if we can query the database
        user_count = User.query.count()
        
        # Test 2: Try to create a test user
        test_email = f"test_{datetime.now().timestamp()}@example.com"
        test_user = User(
            name="Test User",
            email=test_email,
            is_verified=True,
            is_active=True,
            created_at=datetime.now(timezone.utc)
        )
        
        from app import bcrypt
        test_user.set_password("test123", bcrypt)
        
        db.session.add(test_user)
        db.session.flush()
        test_user_id = test_user.id
        db.session.commit()
        
        # Test 3: Verify the user was saved
        saved_user = User.query.filter_by(email=test_email).first()
        
        # Clean up test user
        if saved_user:
            db.session.delete(saved_user)
            db.session.commit()
        
        return jsonify({
            "database_connected": True,
            "users_count": user_count,
            "test_user_created": saved_user is not None,
            "test_user_id": test_user_id if saved_user else None
        }), 200
        
    except Exception as e:
        return jsonify({
            "database_connected": False,
            "error": str(e)
        }), 500
# Middleware to check authentication
def auth_required(f):
    @wraps(f)
    @jwt_required()
    def decorated_function(*args, **kwargs):
        try:
            User = get_user_model()
            user_id = get_jwt_identity()
            user = User.query.get(user_id)
            if not user or not user.is_active:
                return jsonify({'error': 'Unauthorized'}), 401
            return f(user, *args, **kwargs)
        except Exception as e:
            return jsonify({'error': 'Authentication failed'}), 401
    return decorated_function