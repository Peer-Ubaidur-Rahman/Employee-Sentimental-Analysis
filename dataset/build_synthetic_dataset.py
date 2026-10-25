"""
Builds the SYNTHETIC demonstration dataset for Sentinel HR.

*** This data is synthetic. ***  It was written by the project author (template-based
generation + hand-written sentences). It is NOT real employee feedback, it comes from no
external source, and it is released under CC0 (public domain) for this project.

Outputs (columns: feedback, sentiment, source):
  dataset/employee_feedback.csv  - training/evaluation data (template + handwritten)
  dataset/challenge_set.csv      - handwritten sentences NEVER used in training, used as a
                                   harder, less template-shaped check after training.

Run:  python dataset/build_synthetic_dataset.py
"""
import csv
import os
import random

SEED = 42
PER_CLASS_TEMPLATES = 220

TOPICS = [
    "The onboarding process", "Communication from senior leadership", "My direct manager",
    "The workload on my team", "Our performance review process", "The office facilities",
    "Remote work arrangements", "Training and learning opportunities", "Team collaboration",
    "Pay and benefits", "Career progression here", "The internal tooling we use",
    "Meetings on my team", "Work-life balance", "Recognition for good work", "HR support",
    "Project deadlines", "Shift scheduling", "Our team culture", "Staffing levels in my department",
    "Cooperation between departments", "Health and wellness programmes", "Decision making in my department",
    "The quarterly planning process", "Our internal documentation", "The leave and time-off policy",
]

OPENERS = ["", "", "", "Honestly, ", "In my opinion, ", "Overall, ", "From my experience, ", "To be frank, "]

PREDICATES = {
    "Positive": [
        "is well organised and genuinely helpful", "has been excellent this year",
        "makes me feel valued and motivated", "is fair, transparent and supportive",
        "works really well and I am very satisfied", "has improved a lot and I appreciate it",
        "is one of the best things about working here", "is clear, consistent and well managed",
        "gives me the confidence to do my best work", "has been outstanding and I am grateful for it",
        "is respectful and encourages everyone to speak up", "exceeded my expectations",
        "is great and I would recommend it to colleagues", "feels supportive and well resourced",
        "is handled thoughtfully and I am happy with it", "helps me grow and I enjoy it",
        "is reliable and makes my job easier", "is impressive and a real strength of this company",
        "is positive and I feel proud of how we do it", "has been a pleasure and very rewarding",
    ],
    "Negative": [
        "is chaotic and badly managed", "has been disappointing and frustrating",
        "makes me feel undervalued and stressed", "is unfair and not transparent",
        "does not work and I am very dissatisfied", "has got worse and I am unhappy about it",
        "is one of the worst things about working here", "is unclear and inconsistent",
        "is draining and leaves me exhausted", "has been terrible and I am fed up with it",
        "is disrespectful and discourages people from speaking up", "fell far below my expectations",
        "is poor and I would not recommend it to colleagues", "feels unsupported and under resourced",
        "is handled carelessly and I am angry about it", "is not helpful at all",
        "is unreliable and makes my job harder", "is a serious problem that nobody is addressing",
        "is stressful and I feel burned out because of it", "has been a struggle and I am losing motivation",
    ],
    "Neutral": [
        "is adequate and meets basic needs", "is fine, neither good nor bad",
        "has not changed much recently", "is average compared with my previous employer",
        "is okay for now", "works as expected without any surprises",
        "is standard and does what it needs to do", "is acceptable although nothing special",
        "is routine and fairly predictable", "is about the same as last quarter",
        "is neither a strength nor a weakness", "is still in progress so I will wait and see",
        "is typical for a company of this size", "is moderate and I have no strong opinion on it",
        "is reasonable and unremarkable", "is mostly unchanged since the reorganisation",
        "is functional and nothing more", "has had some ups and downs in equal measure",
        "is simply part of the daily routine", "is neither better nor worse than I expected",
    ],
}

HANDWRITTEN_TRAIN = {
    "Positive": [
        "My manager checks in regularly and genuinely listens to my concerns.",
        "I was promoted this year and the process felt fair and open.",
        "The flexible hours let me look after my family without any guilt.",
        "Our team celebrates wins together and nobody is left out.",
        "I get clear goals each quarter and the support I need to reach them.",
        "The new laptops and software made my work noticeably smoother.",
        "I feel safe raising problems because leadership responds constructively.",
        "Mentoring from senior colleagues has helped me grow quickly.",
        "The wellness allowance is generous and I actually use it.",
        "I am proud of the products we build and the people I build them with.",
        "Pay reviews are honest and I feel fairly rewarded for my contribution.",
        "Everyone here is friendly and willing to help when I am stuck.",
        "I rarely work late and my weekends are respected.",
        "Training budgets are real and I have attended two excellent workshops.",
        "Leadership explained the reorganisation clearly and with empathy.",
        "I look forward to Monday mornings because the team is so welcoming.",
        "The onboarding buddy system made me feel part of the team from day one.",
        "I can speak up in meetings and my ideas are taken seriously.",
        "Recognition is frequent and specific, which keeps me motivated.",
        "I love the autonomy I have over how I deliver my projects.",
        "The company really cares about inclusion and it shows in daily behaviour.",
        "My workload is balanced and deadlines are realistic.",
        "I would happily refer my friends to work here.",
        "Management never hesitates to thank us after a hard release.",
    ],
    "Negative": [
        "My manager ignores my emails and takes credit for my work.",
        "I was passed over for promotion and nobody explained why.",
        "I am expected to answer messages late at night and on weekends.",
        "Our team is constantly short staffed and everyone is exhausted.",
        "Goals change every week and I never know what is expected of me.",
        "The old laptops crash daily and nobody will approve replacements.",
        "I do not feel safe raising problems because people get punished for it.",
        "There is no mentoring and I feel completely on my own.",
        "The benefits were cut again and nobody told us in advance.",
        "I dread going to work because of the constant pressure.",
        "Pay reviews are secretive and I feel badly underpaid.",
        "Colleagues compete against each other instead of helping one another.",
        "I regularly work late and my weekends are not respected.",
        "Training requests are always refused with no explanation.",
        "Leadership announced layoffs by email with no empathy whatsoever.",
        "I feel anxious every Sunday evening thinking about the week ahead.",
        "My ideas are dismissed and meetings are a waste of time.",
        "Hard work goes completely unnoticed around here.",
        "Micromanagement makes it impossible to do my job properly.",
        "Favouritism decides who gets the good projects.",
        "My workload is unrealistic and the deadlines are impossible.",
        "I am actively looking for another job because I am so unhappy.",
        "Complaints to HR are ignored and nothing ever changes.",
        "I am burned out and nobody seems to care.",
    ],
    "Neutral": [
        "My manager is around sometimes and communication is occasional.",
        "The promotion process exists but I have not been through it yet.",
        "Working hours are normal and I leave around the usual time.",
        "The team size is about right for the current projects.",
        "Goals are set each quarter and are reviewed at the end of it.",
        "The laptops are a few years old but still do the job.",
        "I have not needed to raise any issues so I cannot comment.",
        "There is a mentoring programme although I have not joined it.",
        "Benefits are in line with what other companies in the area offer.",
        "Some weeks are busy and some are quiet, which is normal for this role.",
        "Pay is about the market average for my role.",
        "I get along with colleagues and we mostly keep to our own tasks.",
        "Overtime happens occasionally around release dates.",
        "Training is available but I have not used it this year.",
        "Leadership sends a monthly update that I usually skim.",
        "The commute takes about forty minutes each way.",
        "Meetings happen on schedule and most are of reasonable length.",
        "I do not have strong opinions about the new expense system.",
        "The canteen is open on weekdays and the prices are average.",
        "The department was reorganised last year and little changed for me.",
        "My workload is manageable at the moment.",
        "I have been here two years and nothing has stood out either way.",
        "Parking and building access work as described in the handbook.",
        "The annual survey was sent out and I filled it in.",
    ],
}

CHALLENGE = {
    "Positive": [
        "I genuinely enjoy coming in; my colleagues make the days fly by.",
        "The support I received during my family emergency was wonderful.",
        "Leadership trusts us to make decisions and backs us when we do.",
        "I have learned more in one year here than in three at my last company.",
        "Our retrospectives lead to real improvements, which I really appreciate.",
        "The team lead is approachable, kind and fair to everyone.",
        "I feel rewarded and respected for the effort I put in.",
        "Great culture, brilliant people and a sensible workload.",
        "The recent policy changes made my life easier and I am thankful.",
        "I am happy here and I do not plan on leaving.",
        "My ideas for the new process were welcomed and implemented.",
        "Excellent communication from management during the merger.",
        "The flexible schedule is fantastic for my well-being.",
        "I feel included and listened to in every team meeting.",
        "Working here has been a very positive experience overall.",
    ],
    "Negative": [
        "Nobody listens to the people doing the actual work.",
        "The constant reorganisations leave everyone confused and demoralised.",
        "I have not had a proper day off in months and it is wearing me down.",
        "Management talks about values but behaves in the opposite way.",
        "My concerns about safety were brushed aside, which is unacceptable.",
        "The new system is slow, buggy and makes my job a nightmare.",
        "I feel invisible and unappreciated in this team.",
        "Pay is far too low for the hours and responsibility expected.",
        "The atmosphere is toxic and gossip spreads quickly.",
        "I cannot see any future for myself here and it is depressing.",
        "Feedback from my manager is harsh, vague and never constructive.",
        "Terrible communication; we heard about the change from the press.",
        "Deadlines are set without asking us and we are blamed when they slip.",
        "I am not satisfied with the way complaints are handled.",
        "Working here has been exhausting and deeply disappointing.",
    ],
    "Neutral": [
        "It is a job that pays the bills and the days are mostly uneventful.",
        "The office moved last month; the new location is about equal to the old one.",
        "Some colleagues are great and some less so, so it evens out.",
        "I use the new tool daily but I have no strong feelings about it.",
        "The policy was updated and it affects me very little.",
        "Management communicates when needed, nothing more and nothing less.",
        "My responsibilities have stayed the same since I joined.",
        "The schedule is regular and the work is steady.",
        "Neither particularly happy nor unhappy with how things are going.",
        "The training I received was standard and covered the basics.",
        "There were a few changes this quarter, none of which impacted me much.",
        "I attended the town hall; it was informative but unremarkable.",
        "The workload fluctuates, which seems usual for this industry.",
        "Benefits and salary are comparable with similar roles elsewhere.",
        "I am still forming an opinion since I only joined recently.",
    ],
}


def _compose(rng, sentiment):
    topic = rng.choice(TOPICS)
    opener = rng.choice(OPENERS)
    predicate = rng.choice(PREDICATES[sentiment])
    if opener:
        topic = topic[0].lower() + topic[1:]
    return f"{opener}{topic} {predicate}."


def build():
    rng = random.Random(SEED)
    rows, seen = [], set()
    for sentiment in ("Positive", "Neutral", "Negative"):
        count, attempts = 0, 0
        while count < PER_CLASS_TEMPLATES and attempts < 20000:
            attempts += 1
            sentence = _compose(rng, sentiment)
            if sentence not in seen:
                seen.add(sentence)
                rows.append((sentence, sentiment, "synthetic-template"))
                count += 1
        for sentence in HANDWRITTEN_TRAIN[sentiment]:
            if sentence not in seen:
                seen.add(sentence)
                rows.append((sentence, sentiment, "synthetic-handwritten"))
    rng.shuffle(rows)

    challenge = []
    for sentiment, sentences in CHALLENGE.items():
        for sentence in sentences:
            assert sentence not in seen, f"challenge sentence leaked into training: {sentence}"
            challenge.append((sentence, sentiment, "synthetic-handwritten-challenge"))

    here = os.path.dirname(os.path.abspath(__file__))
    for name, data in (("employee_feedback.csv", rows), ("challenge_set.csv", challenge)):
        with open(os.path.join(here, name), "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["feedback", "sentiment", "source"])
            writer.writerows(data)
        print(f"wrote {name}: {len(data)} rows")


if __name__ == "__main__":
    build()
