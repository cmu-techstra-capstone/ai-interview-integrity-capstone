"""Hand-written sample interviews for the demo (NOT real candidates, NOT from any dataset).

`mixed` is the best live demo: the first answers are natural, then the "candidate" starts reading
AI-style answers and the running score should climb into the red zone.
"""

Q1 = "Tell me about a time a bug made it to production. What happened?"
Q2 = "Why does software testing matter to you?"
Q3 = "How would you design the testing strategy for a new payments service?"
Q4 = "Describe a disagreement with a teammate and how you resolved it."
Q5 = "What would you do if your service started timing out under load?"

NATURAL = {
    Q1: (
        "Um, yeah, so at my last internship we pushed a change to the checkout page, and, uh, I forgot "
        "to handle the case where the coupon field was empty. So for like an hour some people just got a "
        "blank page. I think it was around two hundred users? My manager Priya caught it from the error "
        "dashboard and, you know, I rolled it back and then wrote a test for it the next morning. "
        "Honestly I was pretty embarrassed, but I learned to test the empty cases first."
    ),
    Q2: (
        "I mean, for me it's kind of personal. I broke something once in a class project right before the "
        "demo, and, uh, it was awful. Now I just feel better when there's a test that, like, tells me "
        "I didn't break the thing I fixed yesterday. It's mostly about sleeping better, I guess."
    ),
    Q3: (
        "Okay so, um, I'd start with the money part, like rounding and currency, because that's where "
        "I've seen weird bugs. Unit tests for that. Then maybe, uh, contract tests with the bank API "
        "because we can't hit it for real every time. I'm not sure about load testing, I haven't done a "
        "lot of that, but I'd want at least something for retries. Sorry, I mean idempotency, that "
        "one, because double charging would be the worst."
    ),
    Q4: (
        "Yeah, so with my teammate Dev we disagreed about using a queue, I thought it was overkill. "
        "We, um, ended up drawing it on a whiteboard for like twenty minutes and I realised the retries "
        "were the problem, not the traffic. He was right, honestly. We shipped his version in about "
        "three days."
    ),
    Q5: (
        "Hmm, first I'd probably look at the dashboard, see if it's the database or the service itself. "
        "I once had this where a missing index made everything slow, so I'd check that kind of thing. "
        "If I'm not sure I'd ask on call, no shame in that. Then maybe scale it up while we figure out "
        "the real cause."
    ),
}

AI_STYLE = {
    Q1: (
        "Certainly. In a previous role, a defect reached production due to insufficient test coverage on "
        "a critical checkout workflow. Firstly, I coordinated with stakeholders to assess the impact. "
        "Secondly, I implemented a rollback to ensure service continuity. Finally, I conducted a "
        "comprehensive root cause analysis and established robust regression testing to mitigate "
        "similar issues. Overall, this experience underscored the importance of proactive quality "
        "assurance and effective cross-functional communication."
    ),
    Q2: (
        "Software testing is crucial because it ensures the reliability, security, and performance of "
        "applications. Furthermore, it enables teams to identify defects early, which significantly "
        "reduces cost and risk. Moreover, a comprehensive testing strategy fosters stakeholder confidence "
        "and facilitates continuous delivery. Ultimately, testing is a pivotal practice that underpins "
        "high-quality, scalable software."
    ),
    Q3: (
        "To design a robust testing strategy for a payments service, I would adopt a layered approach. "
        "First, unit tests would validate core business logic, including currency handling and "
        "rounding. Second, integration tests would verify interactions with external providers. "
        "Third, end-to-end tests would ensure seamless user journeys. Additionally, I would leverage "
        "performance testing to guarantee scalability and security testing to mitigate fraud risks. "
        "In conclusion, this comprehensive approach ensures reliability and compliance."
    ),
    Q4: (
        "In a prior project, I navigated a disagreement by fostering open communication and aligning "
        "on shared objectives. First, I actively listened to my colleague's perspective. Second, we "
        "evaluated trade-offs using data-driven criteria. Ultimately, we reached a consensus that "
        "enhanced both team alignment and project outcomes. This experience reinforced the importance "
        "of collaboration, empathy, and clear communication."
    ),
    Q5: (
        "If a service began timing out under load, I would follow a structured approach. First, I would "
        "review monitoring dashboards to identify bottlenecks. Second, I would analyze logs and traces "
        "to isolate the root cause. Third, I would leverage horizontal scaling and caching to "
        "mitigate immediate impact. Finally, I would implement load testing and capacity planning to "
        "ensure long-term resilience and optimize performance."
    ),
}


def _build(order: list[tuple[str, str]]) -> list[dict]:
    turns: list[dict] = []
    for q, source in order:
        bank = NATURAL if source == "natural" else AI_STYLE
        turns.append({"role": "interviewer", "text": q})
        turns.append({"role": "candidate", "text": bank[q]})
    return turns


SAMPLES = {
    "mixed": {
        "title": "Mixed: natural at first, then AI-style answers (best live demo)",
        "turns": _build([(Q1, "natural"), (Q2, "natural"), (Q3, "ai"), (Q4, "ai"), (Q5, "ai")]),
    },
    "natural": {
        "title": "Unassisted: natural, spontaneous answers",
        "turns": _build([(Q1, "natural"), (Q2, "natural"), (Q3, "natural"), (Q4, "natural"), (Q5, "natural")]),
    },
    "ai": {
        "title": "AI-style: polished, generic answers throughout",
        "turns": _build([(Q1, "ai"), (Q2, "ai"), (Q3, "ai"), (Q4, "ai"), (Q5, "ai")]),
    },
}
