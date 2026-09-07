"""
Run once to create admin accounts.
Command: python seed_admin.py
"""
from app.database import SessionLocal
from app.models.user import User
from app.services.auth import hash_password
from app.config import settings


def seed():
    db = SessionLocal()

    admins = [
        {
            "name": "Abu (Admin)",
            "email": settings.ADMIN_EMAIL_1,
            "phone": "9999999999",
            "password": settings.ADMIN_PASSWORD_1,
        },
        {
            "name": "Father (Admin)",
            "email": settings.ADMIN_EMAIL_2,
            "phone": "8888888888",
            "password": settings.ADMIN_PASSWORD_2,
        }
    ]

    for admin_data in admins:
        exists = db.query(User).filter(
            User.email == admin_data["email"]
        ).first()

        if exists:
            # Update existing admin to have phone_verified = True
            # and token_version if missing
            if exists.token_version is None:
                exists.token_version = 0
            if not exists.phone_verified:
                exists.phone_verified = True
            db.commit()
            print(f"⚠️  Admin already exists: {admin_data['email']} — updated")
            continue

        admin = User(
            name=admin_data["name"],
            email=admin_data["email"],
            phone=admin_data["phone"],
            password_hash=hash_password(admin_data["password"]),
            role="admin",
            phone_verified=True,  # Admins pre-verified
            token_version=0,
        )
        db.add(admin)
        db.commit()
        print(f"✅ Admin created: {admin_data['email']}")

    db.close()
    print("\n🌲 Admin seeding complete!")


if __name__ == "__main__":
    seed()