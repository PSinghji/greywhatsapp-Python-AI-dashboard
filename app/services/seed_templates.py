"""
Seed Script - Pre-built human-like conversation templates.
Hindi/English mix, casual friend-to-friend style.
Run once to populate the conversation_templates collection.
"""
import asyncio
from datetime import datetime, timezone
from app.database import connect_db, get_db


TEMPLATES = [
    # ─── Greetings & Morning ─────────────────────────────────────────────
    {
        "name": "Morning Greeting 1",
        "category": "greetings",
        "language": "mixed",
        "messages": [
            {"text": "Good morning bhai! ☀️ Kaisa hai tu?"},
            {"text": "Aaj ka din kaisa ja raha hai?"},
            {"text": "Chal kuch plan karte hain weekend ke liye"},
        ],
    },
    {
        "name": "Morning Greeting 2",
        "category": "greetings",
        "language": "mixed",
        "messages": [
            {"text": "Uth gaya kya bhai? 😄"},
            {"text": "Subah subah chai pi li?"},
            {"text": "Aaj office jaana hai ya WFH?"},
        ],
    },
    {
        "name": "Morning Greeting 3",
        "category": "greetings",
        "language": "mixed",
        "messages": [
            {"text": "Hey good morning! Kya haal hai?"},
            {"text": "Breakfast kya kiya aaj?"},
        ],
    },
    {
        "name": "Evening Check-in",
        "category": "greetings",
        "language": "mixed",
        "messages": [
            {"text": "Bhai evening ho gayi, kya kar raha hai?"},
            {"text": "Aaj ka kaam khatam hua?"},
            {"text": "Chal bahar chalte hain thoda walk pe"},
        ],
    },
    {
        "name": "Night Greeting",
        "category": "greetings",
        "language": "mixed",
        "messages": [
            {"text": "Bhai so gaya kya? 😴"},
            {"text": "Good night yaar, kal milte hain"},
        ],
    },

    # ─── How Are You / Catch Up ──────────────────────────────────────────
    {
        "name": "Catch Up 1",
        "category": "catchup",
        "language": "mixed",
        "messages": [
            {"text": "Bhai bahut din ho gaye baat nahi hui"},
            {"text": "Sab theek hai na? Family kaisi hai?"},
            {"text": "Kabhi milte hain yaar, miss kar raha hoon"},
        ],
    },
    {
        "name": "Catch Up 2",
        "category": "catchup",
        "language": "mixed",
        "messages": [
            {"text": "Kya chal raha hai life mein?"},
            {"text": "Job kaisi ja rahi hai?"},
            {"text": "Naya kuch hua kya?"},
        ],
    },
    {
        "name": "Catch Up 3",
        "category": "catchup",
        "language": "mixed",
        "messages": [
            {"text": "Hey! Long time no see yaar"},
            {"text": "Kahan gayab ho gaye the?"},
            {"text": "Aaj free ho toh call karo"},
        ],
    },
    {
        "name": "Quick Hello",
        "category": "catchup",
        "language": "mixed",
        "messages": [
            {"text": "Hey bhai! Bas yaad aa gayi teri 😊"},
            {"text": "Kya haal chaal?"},
        ],
    },
    {
        "name": "Checking In",
        "category": "catchup",
        "language": "mixed",
        "messages": [
            {"text": "Bro sab sahi hai na?"},
            {"text": "Kal se reply nahi kiya tune 😅"},
            {"text": "Busy hai kya bahut?"},
        ],
    },

    # ─── Food & Restaurant ───────────────────────────────────────────────
    {
        "name": "Food Chat 1",
        "category": "food",
        "language": "mixed",
        "messages": [
            {"text": "Bhai aaj lunch mein kya khaya?"},
            {"text": "Mujhe toh biryani ka bahut mann hai 🍗"},
            {"text": "Chal kahi bahar chalte hain khaane"},
        ],
    },
    {
        "name": "Food Chat 2",
        "category": "food",
        "language": "mixed",
        "messages": [
            {"text": "Yaar wo naya restaurant try kiya kya?"},
            {"text": "Reviews bahut acche hain uske"},
            {"text": "Weekend pe chalte hain pakka"},
        ],
    },
    {
        "name": "Food Chat 3",
        "category": "food",
        "language": "mixed",
        "messages": [
            {"text": "Bhai pizza order karu kya? 🍕"},
            {"text": "Tu bhi le le apna wala"},
            {"text": "Dominos ya Pizza Hut?"},
        ],
    },
    {
        "name": "Cooking Chat",
        "category": "food",
        "language": "mixed",
        "messages": [
            {"text": "Aaj ghar pe khana banaya maine"},
            {"text": "Dal chawal with achar 😋"},
            {"text": "Tu bhi try kar, recipe bhejta hoon"},
        ],
    },
    {
        "name": "Street Food",
        "category": "food",
        "language": "mixed",
        "messages": [
            {"text": "Yaar wo chaat wala yaad hai?"},
            {"text": "Uski pani puri best hai bhai"},
            {"text": "Aaj shaam ko chalte hain wahan"},
        ],
    },

    # ─── Weekend Plans ───────────────────────────────────────────────────
    {
        "name": "Weekend Plan 1",
        "category": "weekend",
        "language": "mixed",
        "messages": [
            {"text": "Bhai weekend ka kya plan hai?"},
            {"text": "Movie dekhne chalein? Naya wala aaya hai"},
            {"text": "Ya phir ghar pe chill karte hain"},
        ],
    },
    {
        "name": "Weekend Plan 2",
        "category": "weekend",
        "language": "mixed",
        "messages": [
            {"text": "Saturday ko kuch kar rahe ho?"},
            {"text": "Mera plan hai shopping jaane ka"},
            {"text": "Saath chalega kya?"},
        ],
    },
    {
        "name": "Weekend Plan 3",
        "category": "weekend",
        "language": "mixed",
        "messages": [
            {"text": "Yaar Sunday ko cricket khelein?"},
            {"text": "Ground book kar deta hoon"},
            {"text": "Baaki logon ko bhi bula lete hain"},
        ],
    },
    {
        "name": "Lazy Weekend",
        "category": "weekend",
        "language": "mixed",
        "messages": [
            {"text": "Bhai aaj toh bas sona hai 😴"},
            {"text": "Netflix and chill karte hain"},
            {"text": "Koi acchi series suggest kar"},
        ],
    },
    {
        "name": "Road Trip Plan",
        "category": "weekend",
        "language": "mixed",
        "messages": [
            {"text": "Bhai road trip ka mann hai"},
            {"text": "Lonavala ya Mahabaleshwar chalein?"},
            {"text": "Next weekend pakka plan karte hain"},
        ],
    },

    # ─── Weather ─────────────────────────────────────────────────────────
    {
        "name": "Weather Chat 1",
        "category": "weather",
        "language": "mixed",
        "messages": [
            {"text": "Yaar aaj toh bahut garmi hai 🥵"},
            {"text": "AC ke bina toh reh nahi sakte"},
            {"text": "Ice cream kha le thandi wali"},
        ],
    },
    {
        "name": "Weather Chat 2",
        "category": "weather",
        "language": "mixed",
        "messages": [
            {"text": "Baarish ho rahi hai kya tere yahan? 🌧️"},
            {"text": "Yahan toh bahut tez baarish hai"},
            {"text": "Ghar pe hi reh aaj, bahar mat ja"},
        ],
    },
    {
        "name": "Weather Chat 3",
        "category": "weather",
        "language": "mixed",
        "messages": [
            {"text": "Aaj mausam bahut accha hai yaar"},
            {"text": "Thandi hawa chal rahi hai"},
            {"text": "Perfect weather for chai and pakoda ☕"},
        ],
    },
    {
        "name": "Winter Chat",
        "category": "weather",
        "language": "mixed",
        "messages": [
            {"text": "Bhai itni thand hai aaj 🥶"},
            {"text": "Sweater pehen ke baitho"},
            {"text": "Hot chocolate pee le"},
        ],
    },

    # ─── Jokes & Fun ─────────────────────────────────────────────────────
    {
        "name": "Joke 1",
        "category": "jokes",
        "language": "mixed",
        "messages": [
            {"text": "Bhai ek joke suna?"},
            {"text": "Teacher: Tumhara homework kahan hai? Student: Mere dog ne kha liya 😂"},
            {"text": "Haha purana hai but classic"},
        ],
    },
    {
        "name": "Joke 2",
        "category": "jokes",
        "language": "mixed",
        "messages": [
            {"text": "Yaar aaj office mein bahut funny scene hua 😂"},
            {"text": "Boss ne galat email bhej di client ko"},
            {"text": "Poora office has raha tha"},
        ],
    },
    {
        "name": "Meme Share",
        "category": "jokes",
        "language": "mixed",
        "messages": [
            {"text": "Bhai wo meme dekha kya Instagram pe? 😂"},
            {"text": "Bahut funny tha yaar"},
            {"text": "Ruk bhejta hoon tujhe"},
        ],
    },
    {
        "name": "Fun Fact",
        "category": "jokes",
        "language": "mixed",
        "messages": [
            {"text": "Bhai ek interesting fact pata hai?"},
            {"text": "Honey kabhi expire nahi hota"},
            {"text": "3000 saal purana honey bhi kha sakte ho 🍯"},
        ],
    },
    {
        "name": "Funny Story",
        "category": "jokes",
        "language": "mixed",
        "messages": [
            {"text": "Aaj kuch aisa hua ki has has ke pet dukh gaya 😂"},
            {"text": "Auto wale se paise dene gaya toh usne bola keep the change"},
            {"text": "Change sirf 1 rupee tha 🤣"},
        ],
    },

    # ─── Daily Life ──────────────────────────────────────────────────────
    {
        "name": "Work Life 1",
        "category": "daily_life",
        "language": "mixed",
        "messages": [
            {"text": "Yaar aaj meeting bahut boring thi"},
            {"text": "2 ghante waste ho gaye"},
            {"text": "Email se ho jaata sab kuch 😤"},
        ],
    },
    {
        "name": "Work Life 2",
        "category": "daily_life",
        "language": "mixed",
        "messages": [
            {"text": "Bhai promotion mil gayi! 🎉"},
            {"text": "Finally hard work ka result aaya"},
            {"text": "Party toh banti hai ab"},
        ],
    },
    {
        "name": "Traffic Woes",
        "category": "daily_life",
        "language": "mixed",
        "messages": [
            {"text": "Bhai traffic mein phasa hoon 😫"},
            {"text": "1 ghante se move nahi hua"},
            {"text": "Late ho jaunga aaj"},
        ],
    },
    {
        "name": "Shopping Chat",
        "category": "daily_life",
        "language": "mixed",
        "messages": [
            {"text": "Yaar naye shoes lene hain"},
            {"text": "Nike ya Adidas kya suggest karega?"},
            {"text": "Budget 5000 ke andar chahiye"},
        ],
    },
    {
        "name": "Gym Chat",
        "category": "daily_life",
        "language": "mixed",
        "messages": [
            {"text": "Bhai gym jaana shuru kiya hai"},
            {"text": "Bahut pain ho raha hai muscles mein 💪"},
            {"text": "But feel accha hai yaar"},
        ],
    },
    {
        "name": "Health Check",
        "category": "daily_life",
        "language": "mixed",
        "messages": [
            {"text": "Bhai tabiyat kaisi hai ab?"},
            {"text": "Kal toh bola tha fever hai"},
            {"text": "Medicine li? Aaram kar le"},
        ],
    },

    # ─── Sports & Entertainment ──────────────────────────────────────────
    {
        "name": "Cricket Chat 1",
        "category": "sports",
        "language": "mixed",
        "messages": [
            {"text": "Bhai match dekh raha hai? 🏏"},
            {"text": "Kya batting hai yaar!"},
            {"text": "India jeetega pakka aaj"},
        ],
    },
    {
        "name": "Cricket Chat 2",
        "category": "sports",
        "language": "mixed",
        "messages": [
            {"text": "IPL ka kya scene hai?"},
            {"text": "Teri team kaisi chal rahi hai?"},
            {"text": "Meri toh har match haar rahi hai 😅"},
        ],
    },
    {
        "name": "Movie Chat",
        "category": "entertainment",
        "language": "mixed",
        "messages": [
            {"text": "Bhai wo naya movie dekha kya?"},
            {"text": "Reviews toh bahut acche hain"},
            {"text": "Weekend pe dekhte hain saath mein"},
        ],
    },
    {
        "name": "Series Recommendation",
        "category": "entertainment",
        "language": "mixed",
        "messages": [
            {"text": "Yaar ek zabardast series hai Netflix pe"},
            {"text": "Raat bhar binge watch kiya maine"},
            {"text": "Tu bhi dekh, regret nahi hoga"},
        ],
    },
    {
        "name": "Music Chat",
        "category": "entertainment",
        "language": "mixed",
        "messages": [
            {"text": "Bhai naya gaana suna? Bahut accha hai 🎵"},
            {"text": "Loop pe laga rakha hai maine"},
            {"text": "Spotify pe hai, sun ke bata"},
        ],
    },

    # ─── Tech Talk ───────────────────────────────────────────────────────
    {
        "name": "Phone Chat",
        "category": "tech",
        "language": "mixed",
        "messages": [
            {"text": "Bhai naya phone lena hai"},
            {"text": "iPhone ya Samsung kya suggest karega?"},
            {"text": "Budget 30k ke aas paas"},
        ],
    },
    {
        "name": "App Recommendation",
        "category": "tech",
        "language": "mixed",
        "messages": [
            {"text": "Yaar ek bahut accha app mila"},
            {"text": "Productivity ke liye best hai"},
            {"text": "Try kar, free hai"},
        ],
    },
    {
        "name": "Internet Issue",
        "category": "tech",
        "language": "mixed",
        "messages": [
            {"text": "Bhai internet bahut slow chal raha hai 😤"},
            {"text": "Video call bhi nahi ho rahi properly"},
            {"text": "Provider change karna padega shayad"},
        ],
    },

    # ─── Travel ──────────────────────────────────────────────────────────
    {
        "name": "Travel Plan 1",
        "category": "travel",
        "language": "mixed",
        "messages": [
            {"text": "Bhai Goa ka plan bana le 🏖️"},
            {"text": "December mein chalte hain"},
            {"text": "Flight tickets saste mil rahe hain abhi"},
        ],
    },
    {
        "name": "Travel Plan 2",
        "category": "travel",
        "language": "mixed",
        "messages": [
            {"text": "Yaar Manali jaana hai is baar"},
            {"text": "Snow dekhna hai live 🏔️"},
            {"text": "Group trip plan karte hain"},
        ],
    },
    {
        "name": "Travel Memory",
        "category": "travel",
        "language": "mixed",
        "messages": [
            {"text": "Bhai wo Rajasthan trip yaad hai?"},
            {"text": "Kya mast time tha yaar"},
            {"text": "Phir se jaana chahiye"},
        ],
    },

    # ─── Festivals & Events ──────────────────────────────────────────────
    {
        "name": "Festival Wish 1",
        "category": "festivals",
        "language": "mixed",
        "messages": [
            {"text": "Happy Diwali bhai! 🪔✨"},
            {"text": "Bahut saari mithai khana aaj"},
            {"text": "Family ke saath enjoy kar"},
        ],
    },
    {
        "name": "Festival Wish 2",
        "category": "festivals",
        "language": "mixed",
        "messages": [
            {"text": "Eid Mubarak bhai! 🌙"},
            {"text": "Biryani ki dawat de de aaj"},
            {"text": "Bahut din se nahi khayi"},
        ],
    },
    {
        "name": "Birthday Wish",
        "category": "festivals",
        "language": "mixed",
        "messages": [
            {"text": "Happy Birthday yaar! 🎂🎉"},
            {"text": "Party kab de raha hai?"},
            {"text": "Bahut saari wishes aur blessings"},
        ],
    },
    {
        "name": "New Year",
        "category": "festivals",
        "language": "mixed",
        "messages": [
            {"text": "Happy New Year bhai! 🎆"},
            {"text": "Is saal bahut kuch achieve karna hai"},
            {"text": "Tera resolution kya hai?"},
        ],
    },

    # ─── Random / Misc ───────────────────────────────────────────────────
    {
        "name": "Random Chat 1",
        "category": "random",
        "language": "mixed",
        "messages": [
            {"text": "Bhai bore ho raha hoon 😐"},
            {"text": "Kuch karte hain yaar"},
            {"text": "Game khelte hain online?"},
        ],
    },
    {
        "name": "Random Chat 2",
        "category": "random",
        "language": "mixed",
        "messages": [
            {"text": "Yaar ek baat batao"},
            {"text": "Tum log weekend pe kya karte ho usually?"},
            {"text": "Mujhe toh ideas chahiye"},
        ],
    },
    {
        "name": "Motivation",
        "category": "random",
        "language": "mixed",
        "messages": [
            {"text": "Bhai ek acchi baat batata hoon"},
            {"text": "Jab tak try nahi karoge tab tak pata nahi chalega"},
            {"text": "So just go for it! 💪"},
        ],
    },
    {
        "name": "Nostalgia",
        "category": "random",
        "language": "mixed",
        "messages": [
            {"text": "Bhai school ke din yaad aate hain kabhi?"},
            {"text": "Kya time tha yaar wo"},
            {"text": "No tension, no stress, bas masti 😊"},
        ],
    },
    {
        "name": "Pet Chat",
        "category": "random",
        "language": "mixed",
        "messages": [
            {"text": "Bhai mera dog aaj bahut cute lag raha hai 🐕"},
            {"text": "Photo bhejta hoon"},
            {"text": "Tu bhi pet le le yaar, bahut accha lagta hai"},
        ],
    },
    {
        "name": "Quick Reply 1",
        "category": "quick",
        "language": "mixed",
        "messages": [
            {"text": "Ok bhai 👍"},
        ],
    },
    {
        "name": "Quick Reply 2",
        "category": "quick",
        "language": "mixed",
        "messages": [
            {"text": "Haan theek hai"},
        ],
    },
    {
        "name": "Quick Reply 3",
        "category": "quick",
        "language": "mixed",
        "messages": [
            {"text": "Accha sahi hai 😄"},
        ],
    },
    {
        "name": "Quick Reply 4",
        "category": "quick",
        "language": "mixed",
        "messages": [
            {"text": "Haha nice one 😂"},
        ],
    },
    {
        "name": "Quick Reply 5",
        "category": "quick",
        "language": "mixed",
        "messages": [
            {"text": "Chal phir baad mein baat karte hain"},
        ],
    },
]


async def seed_conversation_templates():
    """Seed all conversation templates into the database."""
    db = get_db()
    if db is None:
        print("[Seed] Database not connected")
        return

    # Check if already seeded
    count = await db.conversation_templates.count_documents({})
    if count > 0:
        print(f"[Seed] {count} templates already exist. Skipping seed.")
        return

    now = datetime.now(timezone.utc).isoformat()
    for t in TEMPLATES:
        t["enabled"] = True
        t["createdAt"] = now

    result = await db.conversation_templates.insert_many(TEMPLATES)
    print(f"[Seed] Inserted {len(result.inserted_ids)} conversation templates")

    # Create index
    await db.conversation_templates.create_index("category")
    await db.conversation_templates.create_index("enabled")
    print("[Seed] Indexes created for conversation_templates")


async def main():
    """Standalone seed runner."""
    await connect_db()
    await seed_conversation_templates()


if __name__ == "__main__":
    asyncio.run(main())
