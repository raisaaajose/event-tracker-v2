import asyncio
from prisma import Prisma

INTERESTS = [
    {"category": "Technology & Development", "child": "AI / Machine Learning"},
    {"category": "Technology & Development", "child": "Frontend Development"},
    {"category": "Technology & Development", "child": "Backend Development"},
    {"category": "Technology & Development", "child": "Full-Stack Development"},
    {"category": "Technology & Development", "child": "Cybersecurity"},
    {"category": "Technology & Development", "child": "Cloud Computing"},
    {"category": "Technology & Development", "child": "Robotics & Automation"},
    {"category": "Technology & Development", "child": "Game Development"},
    {"category": "Technology & Development", "child": "UI/UX Design"},
    {"category": "Core Engineering", "child": "Mechanical Engineering"},
    {"category": "Core Engineering", "child": "Aerospace Engineering"},
    {"category": "Core Engineering", "child": "Automotive Engineering"},
    {"category": "Core Engineering", "child": "Electrical & Electronics"},
    {"category": "Core Engineering", "child": "Civil Engineering"},
    {"category": "Core Engineering", "child": "Industrial Engineering"},
    {"category": "Career Opportunities", "child": "Internships"},
    {"category": "Career Opportunities", "child": "Full-Time Placements"},
    {"category": "Career Opportunities", "child": "Company Pre-Placement Talks"},
    {"category": "Career Opportunities", "child": "Resume Workshops"},
    {"category": "Career Opportunities", "child": "Networking Events"},
    {
        "category": "Academics & Research",
        "child": "Study Abroad / Masters Opportunities",
    },
    {"category": "Academics & Research", "child": "PhD Opportunities"},
    {"category": "Academics & Research", "child": "Research Projects & Papers"},
    {"category": "Academics & Research", "child": "Guest Lectures & Seminars"},
    {"category": "Academics & Research", "child": "Technical Workshops"},
    {"category": "Academics & Research", "child": "Hackathons & Competitions"},
    {"category": "Campus Life", "child": "Campus Fests (Tech & Cultural)"},
    {"category": "Campus Life", "child": "Club & Chapter Events"},
    {"category": "Campus Life", "child": "Sports"},
    {"category": "Campus Life", "child": "Health & Wellness"},
    {"category": "Campus Life", "child": "Fine Arts"},
    {"category": "Campus Life", "child": "Volunteering"},
]


async def main():
    db = Prisma()
    await db.connect()
    try:
        existing = await db.interest.find_many()
        existing_pairs = {(i.category, i.child) for i in existing}

        created = 0
        for item in INTERESTS:
            key = (item["category"], item["child"])
            if key in existing_pairs:
                continue
            try:
                await db.interest.create(
                    data={"category": item["category"], "child": item["child"]}
                )
                created += 1
            except Exception as e:
                print(f"Skip ({item['category']} - {item['child']}): {e}")
        print(f"Seeding completed. New records inserted: {created}")
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
