"""
Seed script — creates the database schema and populates it with demo data:
a demo admin account, clinic settings, working hours, treatments, a couple
of blog posts, reviews, and a few sample appointments.

Usage:
    python seed.py
"""
import json
import os
from datetime import date, timedelta, datetime

from app import create_app
from app.extensions import db
from app.models import (
    AdminUser, ClinicSettings, WorkingHours, Treatment, Patient, Appointment,
    BlogPost, Review, AppointmentHistory
)
from app.utils import generate_public_code, slugify


TREATMENTS = [
    dict(
        name="General Checkup", icon="tooth", duration_minutes=30,
        short_description="A thorough exam to catch problems early and keep your smile healthy.",
        intro="Regular checkups are the foundation of good oral health.",
        what_is_it="A general checkup includes a visual exam, a review of your dental history, and often X-rays.",
        when_needed="Recommended every six months, or sooner if you notice pain, sensitivity, or changes.",
        symptoms="Routine — no symptoms required. Book sooner if you notice pain, bleeding gums, or sensitivity.",
        procedure="The dentist examines your teeth, gums, and bite, and discusses any findings with you.",
        recovery="No recovery time needed — you can return to normal activities immediately.",
        faqs=[{"q": "How often should I get a checkup?", "a": "Most patients benefit from a checkup every six months."}],
    ),
    dict(
        name="Dental Cleaning", icon="sparkle", duration_minutes=30,
        short_description="Professional cleaning to remove plaque and tartar buildup.",
        intro="A cleaning helps prevent cavities and gum disease.",
        what_is_it="Using specialized tools, we remove plaque and tartar that brushing alone can't reach.",
        when_needed="Typically every six months as part of preventive care.",
        symptoms="No specific symptoms needed — this is a preventive treatment.",
        procedure="Gentle scaling, polishing, and a fluoride treatment if recommended.",
        recovery="You may notice mild sensitivity for a day, which usually resolves quickly.",
        faqs=[{"q": "Does cleaning hurt?", "a": "Most patients feel little to no discomfort during a routine cleaning."}],
    ),
    dict(
        name="Teeth Whitening", icon="sparkle", duration_minutes=45,
        short_description="Brighten your smile with a safe, professional whitening treatment.",
        intro="Professional whitening is faster and more even than over-the-counter kits.",
        what_is_it="A whitening gel is applied to lift stains and discoloration from the enamel.",
        when_needed="Whenever you'd like a brighter smile — great before special occasions.",
        symptoms="Not symptom-driven; this is a cosmetic treatment.",
        procedure="Protective gel is applied to gums, whitening agent applied to teeth, then activated.",
        recovery="Some temporary sensitivity is common and typically fades within a day or two.",
        faqs=[{"q": "How long do results last?", "a": "Results vary but often last several months with good oral hygiene."}],
    ),
    dict(
        name="Dental Filling", icon="tooth", duration_minutes=30,
        short_description="Restore teeth affected by cavities with a durable filling.",
        intro="Fillings restore the shape and function of a tooth damaged by decay.",
        what_is_it="A filling replaces the portion of tooth structure removed to treat a cavity.",
        when_needed="When a cavity is diagnosed, ideally before it grows larger.",
        symptoms="Tooth sensitivity, visible dark spots, or mild pain when chewing.",
        procedure="The decayed portion is removed and the tooth is filled with a tooth-colored material.",
        recovery="Numbness wears off within a few hours; you can eat once sensation returns.",
        faqs=[{"q": "Will it hurt during the procedure?", "a": "Local anesthesia is used, so the area is numbed beforehand."}],
    ),
    dict(
        name="Root Canal Treatment", icon="tooth", duration_minutes=60,
        short_description="Relieve pain and save an infected tooth from extraction.",
        intro="Root canal therapy treats infection deep inside the tooth.",
        what_is_it="The infected pulp is removed, the canal cleaned, and the tooth sealed.",
        when_needed="When infection or severe decay reaches the tooth's inner pulp.",
        symptoms="Persistent tooth pain, sensitivity to hot/cold, swelling, or a darkening tooth.",
        procedure="Performed under local anesthesia over one or more visits.",
        recovery="Mild soreness for a few days is common and manageable with over-the-counter pain relief.",
        faqs=[{"q": "Is a root canal painful?", "a": "With modern anesthesia, most patients report the procedure itself is not painful."}],
    ),
    dict(
        name="Tooth Extraction", icon="tooth", duration_minutes=30,
        short_description="Safe removal of a damaged or problematic tooth.",
        intro="Extraction may be recommended when a tooth cannot be saved.",
        what_is_it="The tooth is carefully removed from its socket.",
        when_needed="Severe decay, crowding, or impacted wisdom teeth.",
        symptoms="Significant pain, infection, or a tooth that is beyond repair.",
        procedure="Local anesthesia is administered before the tooth is removed.",
        recovery="Follow aftercare instructions; most discomfort resolves within a few days.",
        faqs=[{"q": "How long is recovery?", "a": "Most people feel back to normal within a few days, following aftercare instructions."}],
    ),
    dict(
        name="Dental Implant", icon="tooth", duration_minutes=90,
        short_description="A long-term solution for replacing missing teeth.",
        intro="Implants provide a stable, natural-looking replacement for missing teeth.",
        what_is_it="A titanium post is placed in the jawbone to support a replacement tooth.",
        when_needed="When one or more teeth are missing and a durable solution is desired.",
        symptoms="Not symptom-driven — this is a restorative option after tooth loss.",
        procedure="Performed in stages, with healing time between the implant placement and the final crown.",
        recovery="Healing can take a few months; follow-up visits monitor progress.",
        faqs=[{"q": "How long do implants last?", "a": "With good care, implants can last many years."}],
    ),
    dict(
        name="Braces / Orthodontics", icon="tooth", duration_minutes=45,
        short_description="Straighten teeth and correct bite issues over time.",
        intro="Orthodontic treatment gradually moves teeth into better alignment.",
        what_is_it="Braces apply gentle, continuous pressure to reposition teeth.",
        when_needed="For crowding, gaps, or bite misalignment.",
        symptoms="Crowded or crooked teeth, difficulty biting or chewing comfortably.",
        procedure="Brackets and wires (or clear aligners) are fitted and adjusted periodically.",
        recovery="Mild discomfort after adjustments is normal and temporary.",
        faqs=[{"q": "How long does treatment take?", "a": "Treatment length varies by case, often between several months and a few years."}],
    ),
    dict(
        name="Crowns & Bridges", icon="tooth", duration_minutes=60,
        short_description="Restore and protect damaged teeth or replace missing ones.",
        intro="Crowns and bridges restore strength, function, and appearance.",
        what_is_it="A crown caps a damaged tooth; a bridge replaces one or more missing teeth.",
        when_needed="After a root canal, for a cracked tooth, or to replace missing teeth.",
        symptoms="A weakened, cracked, or heavily filled tooth, or a gap from a missing tooth.",
        procedure="The tooth is prepared, an impression taken, and a custom restoration fitted.",
        recovery="Minimal downtime; some sensitivity possible until you adjust to the new restoration.",
        faqs=[{"q": "How long do crowns last?", "a": "With proper care, crowns often last a decade or more."}],
    ),
    dict(
        name="Pediatric Dentistry", icon="tooth", duration_minutes=30,
        short_description="Gentle, friendly dental care designed for children.",
        intro="We make dental visits comfortable and even fun for young patients.",
        what_is_it="Preventive and restorative care tailored to children's developing teeth.",
        when_needed="Starting around a child's first birthday, and at regular checkups after.",
        symptoms="Routine care, or if a child reports tooth pain or sensitivity.",
        procedure="A gentle exam and cleaning, with extra time spent easing any anxiety.",
        recovery="No recovery time needed for routine visits.",
        faqs=[{"q": "When should my child's first visit be?", "a": "Most guidelines recommend a first visit around age one."}],
    ),
    dict(
        name="Cosmetic Dentistry", icon="sparkle", duration_minutes=60,
        short_description="Enhance the appearance of your smile with tailored options.",
        intro="From whitening to veneers, cosmetic dentistry improves smile aesthetics.",
        what_is_it="A range of treatments designed to improve the look of your teeth.",
        when_needed="Whenever you'd like to improve the shape, color, or alignment of your smile.",
        symptoms="Not symptom-driven — based on your aesthetic goals.",
        procedure="Varies by treatment; discussed and planned during a consultation.",
        recovery="Depends on the specific procedure chosen.",
        faqs=[{"q": "What options are available?", "a": "Options include whitening, veneers, and reshaping, discussed during your consultation."}],
    ),
    dict(
        name="Emergency Dental Care", icon="alert", duration_minutes=30,
        short_description="Urgent care for dental pain, trauma, or injury.",
        intro="We prioritize urgent dental issues to relieve pain quickly.",
        what_is_it="Same-day or next-available care for dental emergencies.",
        when_needed="Severe pain, trauma, swelling, or a knocked-out tooth.",
        symptoms="Intense pain, swelling, bleeding, or a broken/knocked-out tooth.",
        procedure="Varies based on the emergency; the priority is stabilizing and relieving pain.",
        recovery="Depends on the treatment provided.",
        faqs=[{"q": "What counts as a dental emergency?", "a": "Severe pain, swelling, trauma, or a knocked-out tooth all warrant urgent care."}],
    ),
]

BLOG_POSTS = [
    dict(
        title="5 Simple Habits for a Healthier Smile",
        category="Oral Health",
        tags="oral hygiene, prevention",
        excerpt="Small daily habits can make a big difference in your long-term dental health.",
        content=(
            "Good oral health starts with consistency. Brushing twice a day, flossing daily, and "
            "limiting sugary snacks all add up over time. Regular checkups let your dentist catch "
            "small issues before they become bigger problems. Staying hydrated also helps maintain "
            "healthy saliva flow, which naturally protects your teeth. Finally, replacing your "
            "toothbrush every three months keeps your cleaning routine effective."
        ),
    ),
    dict(
        title="What to Expect During Your First Root Canal",
        category="Treatments",
        tags="root canal, procedures",
        excerpt="Understanding the process can help ease any anxiety about root canal treatment.",
        content=(
            "Root canal treatment has a reputation for being uncomfortable, but modern techniques "
            "and anesthesia make the procedure far more comfortable than most people expect. During "
            "your visit, the area is numbed, the infected pulp is carefully removed, and the tooth "
            "is cleaned and sealed. Most patients report feeling only mild soreness afterward, "
            "manageable with over-the-counter pain relief. Following your dentist's aftercare "
            "guidance helps ensure smooth healing."
        ),
    ),
]

REVIEWS = [
    dict(patient_name="Amelia R.", rating=5, review_text="Such a calming environment — I actually don't dread appointments anymore."),
    dict(patient_name="James T.", rating=5, review_text="The online booking made scheduling around my work hours so easy."),
    dict(patient_name="Priya K.", rating=4, review_text="Very thorough explanation of my treatment options before starting anything."),
]


def run_seed():
    app = create_app(os.environ.get("FLASK_ENV", "development"))
    with app.app_context():
        db.create_all()

        # --- Admin user --------------------------------------------------
        admin_email = app.config["ADMIN_EMAIL"].lower().strip()
        admin = AdminUser.query.filter_by(email=admin_email).first()
        if not admin:
            admin = AdminUser(name="Clinic Admin", email=admin_email)
            admin.set_password(app.config["ADMIN_PASSWORD"])
            db.session.add(admin)
            print(f"Created admin account: {admin_email}")
        else:
            print(f"Admin account already exists: {admin_email}")

        # --- Clinic settings (singleton) ---------------------------------
        settings = ClinicSettings.get()
        db.session.add(settings)

        # --- Working hours -------------------------------------------------
        if WorkingHours.query.count() == 0:
            defaults = {
                0: ("10:00", "19:00"),  # Monday
                1: ("10:00", "19:00"),
                2: ("10:00", "19:00"),
                3: ("10:00", "19:00"),
                4: ("10:00", "19:00"),
                5: ("10:00", "16:00"),  # Saturday
                6: (None, None),        # Sunday closed
            }
            for weekday, (start, end) in defaults.items():
                is_open = start is not None
                db.session.add(WorkingHours(
                    weekday=weekday, is_open=is_open,
                    open_time=start or "10:00", close_time=end or "19:00",
                    break_start="13:00" if is_open else None,
                    break_end="14:00" if is_open else None,
                ))
            print("Created default working hours.")

        # --- Treatments ------------------------------------------------------
        if Treatment.query.count() == 0:
            for i, data in enumerate(TREATMENTS):
                faqs = data.pop("faqs", [])
                t = Treatment(slug=slugify(data["name"]), display_order=i, **data)
                t.faq_json = json.dumps(faqs)
                db.session.add(t)
            print(f"Created {len(TREATMENTS)} demo treatments.")

        db.session.commit()

        # --- Blog posts --------------------------------------------------------
        if BlogPost.query.count() == 0:
            for i, data in enumerate(BLOG_POSTS):
                post = BlogPost(
                    slug=slugify(data["title"]), is_published=True,
                    published_at=datetime.utcnow() - timedelta(days=i),
                    **data
                )
                db.session.add(post)
            print(f"Created {len(BLOG_POSTS)} demo blog posts.")

        # --- Reviews -------------------------------------------------------
        if Review.query.count() == 0:
            for data in REVIEWS:
                db.session.add(Review(**data))
            print(f"Created {len(REVIEWS)} demo reviews.")

        db.session.commit()

        # --- Demo appointments (optional) -----------------------------------
        if Appointment.query.count() == 0:
            demo_patient = Patient.query.filter_by(phone="+15550001111").first()
            if not demo_patient:
                demo_patient = Patient(
                    full_name="Jordan Smith", phone="+15550001111", email="jordan@example.com",
                    age=34, patient_type="new"
                )
                db.session.add(demo_patient)
                db.session.flush()

            cleaning = Treatment.query.filter_by(name="Dental Cleaning").first()
            if cleaning:
                appt_date = date.today() + timedelta(days=2)
                appt = Appointment(
                    public_code=generate_public_code(), patient_id=demo_patient.id,
                    treatment_id=cleaning.id, date=appt_date, time="11:00",
                    duration_minutes=cleaning.duration_minutes, status="confirmed",
                )
                db.session.add(appt)
                db.session.flush()
                db.session.add(AppointmentHistory(
                    appointment_id=appt.id, action="created",
                    details="Demo appointment created by seed script", performed_by="system"
                ))
                print("Created 1 demo appointment.")

        db.session.commit()
        print("\nSeed complete.")
        print(f"Admin login: {admin_email} / (see ADMIN_PASSWORD in your .env)")


if __name__ == "__main__":
    run_seed()
