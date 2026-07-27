"""
Run using command python seed_admin.py
"""

from app.database import SessionLocal
from app.models.user import User
from app.services.auth import hash_password
from app.config import settings

def seed():
    db=SessionLocal()
    admins=[
        {
            "name":"Person1",
            "email": settings.ADMIN_EMAIL_1,
            "phone": "99999999",
            "password": settings.ADMIN_PASSWORD_1
        },
        {
            "name":"Person2",
            "email": settings.ADMIN_EMAIL_2,
            "phone": "9675299951",
            "password": settings.ADMIN_PASSWORD_2
        }
    ]

    for admin_data in admins:
        # Skip if already exists
        exists = db.query(User).filter(
            User.email == admin_data["email"]
        ).first()

        if exists:
            print(f"⚠️  Admin already exists: {admin_data['email']}")
            continue

        admin = User(
            name=admin_data["name"],
            email=admin_data["email"],
            phone=admin_data["phone"],
            password_hash=hash_password(admin_data["password"]),
            role="admin"
        )
        db.add(admin)
        db.commit()
        print(f"✅ Admin created: {admin_data['email']}")

    db.close()
    print("\n🌲 Admin seeding complete!")

if __name__ == "__main__":
    seed()