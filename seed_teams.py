from app import db, Team, app

with app.app_context():
    Team.query.delete()
    db.session.commit()
    print("All teams deleted.")

    teams = [
        Team(name="Alpha", city="Cebu", description="Main CQB team"),
        Team(name="Bravo", city="Davao", description="Sniper unit"),
        Team(name="Charlie", city="Manila", description="Support/Assault team"),
    ]
    db.session.bulk_save_objects(teams)
    db.session.commit()
    print("Teams seeded!")