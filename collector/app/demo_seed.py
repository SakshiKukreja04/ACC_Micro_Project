"""
Offline demo dataset.

Used only when live feeds are unreachable (SEED_DEMO_DATA=auto and the database is empty) or when
explicitly requested (SEED_DEMO_DATA=true / `python -m app.main --seed-demo`).

Every story is fictional, every publisher is prefixed with "Demo", and every URL points to the
non-routable demo.newsroom.local domain, so demo content can never be mistaken for real reporting.
Several stories are covered by multiple demo outlets with different angles so that story clustering,
the Perspective Lens and the Story Timeline can be demonstrated offline.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from app.normalizer import compute_content_hash

# (hours_ago, source, category, title, description, content)
DEMO_ARTICLES = [
    # --- Story cluster: climate accord (3 outlets, different framing) -------------------------------
    (3, "Demo Chronicle", "World", "World leaders agree landmark climate accord to cut methane emissions",
     "Delegates from 140 countries agreed to cut methane emissions by 40 percent by 2035 at the Northbridge climate summit.",
     "Delegates from 140 countries agreed on Saturday to cut methane emissions by 40 percent by 2035, closing the Northbridge "
     "climate summit with a deal many negotiators called historic. The accord creates a shared fund to help developing nations "
     "capture methane from landfills and oil fields. Summit chair Elena Marsh said the agreement proves cooperation is still "
     "possible. Environmental groups welcomed the deal and urged quick implementation."),
    (5, "Demo Tribune", "World", "Climate accord criticised as methane targets lack enforcement",
     "Critics say the Northbridge climate summit methane accord has no penalties for countries that miss the 2035 target.",
     "The methane accord reached at the Northbridge climate summit has drawn criticism because it contains no enforcement "
     "mechanism. Countries that miss the 40 percent methane cut by 2035 face no penalties, and the shared fund is voluntary. "
     "Several energy analysts warned that previous climate pledges failed for the same reason. Industry groups also raised "
     "concerns about the cost of new methane monitoring rules."),
    (4, "Demo Wire", "World", "Northbridge summit ends with methane deal and new climate fund",
     "The Northbridge climate summit concluded with 140 countries backing a 40 percent methane reduction by 2035.",
     "The Northbridge climate summit concluded with 140 countries backing a 40 percent methane reduction by 2035. The accord "
     "establishes a climate fund for methane capture projects, with the first contributions expected next year. Negotiators "
     "said details on monitoring would be finalised at technical meetings in the spring. Officials from both large and small "
     "economies signed the final text."),

    # --- Story cluster: interest rates --------------------------------------------------------------
    (6, "Demo Finance Insight", "Business", "Central bank holds interest rates steady as inflation cools",
     "The Reserve Bank of Northland kept its benchmark interest rate at 6.25 percent, citing easing food inflation.",
     "The Reserve Bank of Northland kept its benchmark interest rate unchanged at 6.25 percent on Thursday. Governor Arun Mehra "
     "said inflation has cooled for three consecutive months as food prices eased. Markets rose after the announcement, with "
     "banking shares leading gains. Economists expect a possible rate cut early next year if the trend continues."),
    (7, "Demo Chronicle", "Business", "Borrowers wait longer for relief as central bank keeps rates unchanged",
     "Home buyers and small businesses face higher loan costs after the Reserve Bank of Northland held interest rates at 6.25 percent.",
     "Home buyers and small businesses will wait longer for cheaper loans after the Reserve Bank of Northland held its interest "
     "rate at 6.25 percent. Real estate developers said sales have slowed because monthly payments remain high. Small business "
     "owners described credit as tight. The central bank said inflation must fall further before it can cut rates."),
    (6, "Demo Wire", "Business", "Reserve Bank of Northland keeps benchmark rate at 6.25 percent",
     "The central bank left interest rates unchanged and said it will watch inflation data before acting.",
     "The Reserve Bank of Northland left its benchmark interest rate at 6.25 percent, in line with economists' expectations. "
     "The monetary policy committee voted five to one to hold rates. The bank raised its growth forecast slightly to 6.8 percent "
     "and said inflation is moving toward its target. The next policy review is scheduled in eight weeks."),

    # --- Story cluster: open AI model --------------------------------------------------------------
    (2, "Demo TechNow", "Technology", "Velora AI releases open language model that tops reasoning benchmark",
     "Startup Velora AI released an open-weight language model that set a new benchmark score for language understanding.",
     "Startup Velora AI released an open-weight language model on Tuesday that set a new record on a popular reasoning benchmark. "
     "The model can run on a single graphics card, which the company says will help universities and small developers. Velora AI "
     "published the training details and model weights under a permissive licence. Early testers praised its coding and maths skills."),
    (3, "Demo Tribune", "Technology", "Experts warn open AI model from Velora could be misused",
     "Security researchers raised concerns that Velora AI's freely available language model lacks safeguards.",
     "Security researchers raised concerns that the open language model released by Velora AI could be misused because anyone can "
     "download and modify it. They said open models make it harder to block harmful uses such as spam and scams. Velora AI said it "
     "tested the model for safety and will publish a responsible use guide. Policy makers are debating rules for open AI models."),
    (2, "Demo Wire", "Technology", "Velora AI open model release draws developers and regulators' attention",
     "Velora AI's new open-weight language model was downloaded more than 200,000 times in its first day.",
     "Velora AI's new open-weight language model was downloaded more than 200,000 times in its first day, according to the company. "
     "The release topped a reasoning benchmark and runs on a single graphics card. Regulators said they are studying how existing "
     "rules apply to open AI models. Competitors are expected to respond with their own releases."),

    # --- Story cluster: electric buses -------------------------------------------------------------
    (9, "Demo Chronicle", "India", "City launches 500 electric buses in push for cleaner, greener transport",
     "Northbridge Municipal Corporation launched 500 electric buses that will replace ageing diesel buses across 40 routes.",
     "Northbridge Municipal Corporation launched 500 electric buses on Monday to replace ageing diesel buses across 40 routes. "
     "Officials said the fleet will cut carbon emissions by 60,000 tonnes a year and reduce air pollution near busy junctions. "
     "Commuters welcomed the quieter, air conditioned buses. The city plans to add 300 more buses next year."),
    (10, "Demo Tribune", "India", "Charging delays and fare questions cloud city's electric bus rollout",
     "Only half of the charging stations for Northbridge's new electric buses are ready, raising concerns about service gaps.",
     "Only half of the charging stations needed for Northbridge's 500 new electric buses are ready, according to transport officials. "
     "Drivers reported long waits to recharge during the first week, causing gaps on some routes. Commuter groups also asked whether "
     "fares will rise to cover the cost of the electric fleet. The municipal corporation said all charging depots will be finished within three months."),

    # --- Story cluster: underdog final ---------------------------------------------------------------
    (14, "Demo Sports Central", "Sports", "Underdogs stun champions in thrilling cup final",
     "Riverside United beat defending champions Harbour City 3-2 after extra time to lift their first national cup.",
     "Riverside United beat defending champions Harbour City 3-2 after extra time to win their first national cup. Teenage striker "
     "Kabir Rao scored the winning goal in the 112th minute. Riverside were ranked 18th at the start of the season. Fans celebrated "
     "late into the night as the coach praised the team's belief and fitness."),
    (13, "Demo Wire", "Sports", "Riverside United win national cup final 3-2 after extra time",
     "Kabir Rao's extra-time goal gave Riverside United a 3-2 win over Harbour City in the national cup final.",
     "Riverside United won the national cup final 3-2 against Harbour City after extra time. Kabir Rao scored the decisive goal in "
     "the 112th minute after Harbour City had twice taken the lead. Harbour City's coach said tired legs cost his team. It is the "
     "biggest upset in the competition for two decades."),

    # --- Story cluster: cancer research -------------------------------------------------------------
    (20, "Demo HealthDaily", "Health", "Breakthrough in cancer research offers new hope for patients",
     "A clinical trial found that a new immunotherapy shrank tumours in 62 percent of patients with advanced skin cancer.",
     "A clinical trial found that a new immunotherapy treatment shrank tumours in 62 percent of patients with advanced skin cancer. "
     "Researchers at Northbridge Medical Institute said side effects were mild for most patients. The treatment trains the immune "
     "system to recognise cancer cells. Doctors cautioned that larger trials are needed before the therapy can be approved."),
    (22, "Demo Science Today", "Health", "Immunotherapy trial results promising but early, scientists say",
     "Scientists welcomed new skin cancer immunotherapy results but noted the trial involved only 120 patients.",
     "Scientists welcomed results from a new skin cancer immunotherapy trial but noted it involved only 120 patients. The treatment "
     "shrank tumours in 62 percent of participants, according to Northbridge Medical Institute. Independent experts said longer "
     "follow up is needed to know whether patients live longer. A larger international trial will begin next year."),

    # --- Single stories ----------------------------------------------------------------------------
    (1, "Demo Science Today", "Science", "New study reveals secrets of the human brain during sleep",
     "Researchers mapped how the brain replays memories during deep sleep, strengthening learning.",
     "Researchers used high resolution brain scans to map how the brain replays memories during deep sleep. The study of 300 volunteers "
     "found that memories replayed more often were remembered better the next day. Scientists say the findings could help treat memory "
     "disorders. The team now plans to study how age affects memory replay."),
    (8, "Demo Science Today", "Science", "Space telescope spots water vapour on distant rocky planet",
     "Astronomers detected water vapour in the atmosphere of a rocky exoplanet 48 light years away.",
     "Astronomers detected water vapour in the atmosphere of a rocky planet 48 light years from Earth using a space telescope. "
     "The planet orbits a small red star and is slightly larger than Earth. Scientists said the discovery does not mean life exists "
     "there, but it makes the planet a priority for future observations. The findings were published in a peer reviewed journal."),
    (11, "Demo TechNow", "Technology", "Data breach at ticketing platform exposes 2 million customer records",
     "Hackers accessed names, emails and partial card details of two million customers of TicketNest.",
     "Ticketing platform TicketNest said hackers accessed names, email addresses and partial card details of two million customers. "
     "The company said passwords were encrypted and full card numbers were not stored. Customers are advised to watch for phishing "
     "emails. Cyber security experts said the breach shows the need for stronger security at online retailers."),
    (16, "Demo TechNow", "Technology", "Smartphone makers bet on longer software support to win buyers",
     "Major smartphone brands now promise up to seven years of security updates for new phones.",
     "Major smartphone makers are promising up to seven years of security updates for new phones as buyers keep devices longer. "
     "Analysts said longer support reduces electronic waste and improves resale value. Budget brands are under pressure to match the "
     "promise. Consumer groups welcomed the change but asked for clear labels on support periods."),
    (12, "Demo Finance Insight", "Business", "Markets react to global trade policy changes",
     "Stock markets fell 1.2 percent as investors weighed new tariffs announced by several major economies.",
     "Stock markets fell 1.2 percent on Wednesday as investors weighed new tariffs announced by several major economies. Export "
     "focused companies in steel and electronics saw the biggest losses. Analysts said uncertainty about trade policy could slow "
     "investment. Bond prices rose as investors looked for safer assets."),
    (18, "Demo Finance Insight", "Business", "Electric vehicle startup raises $300 million to expand battery plant",
     "Voltaro Motors raised new funding to triple production at its battery factory.",
     "Electric vehicle startup Voltaro Motors raised 300 million dollars to triple production at its battery factory. The company "
     "said the plant will create 4,000 jobs over three years. Investors cited strong demand for affordable electric scooters and cars. "
     "Voltaro plans to begin exporting batteries next year."),
    (15, "Demo HealthDaily", "Health", "Doctors issue heatwave advisory as temperatures cross 44 degrees",
     "Health officials urged residents to stay hydrated and avoid outdoor work in the afternoon during the heatwave.",
     "Health officials issued a heatwave advisory as temperatures crossed 44 degrees Celsius in several districts. Doctors urged "
     "people to drink water often, avoid outdoor work between noon and four, and check on elderly neighbours. Hospitals reported a "
     "rise in heat exhaustion cases. Cooling centres have opened in public buildings."),
    (26, "Demo HealthDaily", "Health", "Study links daily walking to lower risk of heart disease",
     "Adults who walked 7,000 steps a day had a 30 percent lower risk of heart disease, a large study found.",
     "Adults who walked about 7,000 steps a day had a 30 percent lower risk of heart disease than those who walked less, a study of "
     "50,000 people found. The benefits appeared even for people who started walking later in life. Researchers said walking is a "
     "simple and free way to improve health. They recommended building activity into daily routines."),
    (19, "Demo Entertainment Buzz", "Entertainment", "Blockbuster sequel wins hearts worldwide on opening weekend",
     "The animated sequel Skyward Tales 2 earned $210 million globally in its opening weekend.",
     "The animated sequel Skyward Tales 2 earned 210 million dollars globally in its opening weekend, beating forecasts. Audiences "
     "praised its music and emotional story. The studio said the film performed especially well in Asia and Latin America. A third "
     "film has already been announced."),
    (30, "Demo Entertainment Buzz", "Entertainment", "Independent film festival celebrates first-time directors",
     "The Northbridge Film Festival awarded its top prize to a debut drama about a family-run bakery.",
     "The Northbridge Film Festival awarded its top prize to a debut drama about a family run bakery facing closure. Seventeen of the "
     "festival's 40 films were made by first time directors. Organisers said streaming platforms are buying more independent films. "
     "The festival attracted a record 80,000 visitors."),
    (17, "Demo Chronicle", "Politics", "Parliament passes data protection bill after long debate",
     "Lawmakers approved a data protection bill that gives citizens the right to delete personal data held by companies.",
     "Lawmakers approved a data protection bill after a 12 hour debate. The law gives citizens the right to see and delete personal "
     "data held by companies and creates an independent data protection board. Opposition members said the board needs more "
     "independence. Technology companies will have 18 months to comply."),
    (24, "Demo Wire", "Politics", "Election commission announces dates for state assembly polls",
     "Voting for the state assembly will take place in three phases starting next month.",
     "The election commission announced that voting for the state assembly will take place in three phases starting next month. "
     "More than 52 million voters are eligible, including 2 million first time voters. The commission said polling stations will "
     "have ramps and help desks for elderly and disabled voters. Results will be announced on a single day."),
    (21, "Demo Sports Central", "Sports", "National cricket team names three uncapped players for tour",
     "Selectors named three uncapped players in a 16-member squad for next month's five-match series.",
     "Selectors named three uncapped players in a 16 member squad for next month's five match cricket series. The new faces include "
     "a fast bowler who took 45 wickets in the domestic season. The captain said the tour is a chance to build depth before the world "
     "cup. The first match will be played in a day night format."),
    (28, "Demo Science Today", "Science", "Monsoon arrives early, raising hopes for strong harvest",
     "The monsoon reached the coast four days early, and forecasters expect above-normal rainfall.",
     "The monsoon reached the coast four days earlier than usual, and forecasters expect above normal rainfall this season. Farmers "
     "welcomed the news as reservoirs were running low after a hot summer. Agricultural experts said good rain could help lower food "
     "prices. Officials warned of possible flooding in low lying areas."),
    (33, "Demo Tribune", "World", "Flooding forces thousands to evacuate in coastal region",
     "Heavy rain caused rivers to overflow, forcing 12,000 people to move to relief camps.",
     "Heavy rain caused rivers to overflow in the coastal region, forcing 12,000 people to move to relief camps. Rescue teams used "
     "boats to reach villages cut off by water. Officials said no deaths had been reported but crops on thousands of hectares were "
     "damaged. More rain is forecast for the next two days."),
    (36, "Demo Chronicle", "General", "Public libraries see surge in young readers after free membership drive",
     "Library visits by students doubled after the city made memberships free for anyone under 21.",
     "Library visits by students doubled after the city made memberships free for anyone under 21. Librarians said comic books, "
     "science fiction and exam guides are the most borrowed titles. Several libraries have extended opening hours to accommodate "
     "demand. The city plans to open two new branches next year."),
    (40, "Demo Wire", "Technology", "Satellite internet service expands to 2,000 remote villages",
     "A satellite broadband service connected schools and health centres in 2,000 remote villages.",
     "A satellite broadband service connected schools and health centres in 2,000 remote villages, officials said. Teachers reported "
     "that students can now attend online classes and access digital libraries. Health workers use the connection for video "
     "consultations with doctors in cities. The service will expand to 5,000 more villages next year."),
]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:80]


def build_demo_articles(now: datetime | None = None) -> List[Dict]:
    now = now or datetime.now(timezone.utc)
    articles = []
    for hours_ago, source, category, title, description, content in DEMO_ARTICLES:
        url = f"https://demo.newsroom.local/{_slug(source)}/{_slug(title)}"
        published = now - timedelta(hours=hours_ago)
        articles.append({
            "title": title,
            "canonical_url": url,
            "source_name": source,
            "category": category,
            "description": description,
            "content": content,
            "published_at": published,
            "collected_at": now,
            "content_hash": compute_content_hash(url, title),
            "processing_status": "pending",
            "processing_attempts": 0,
            "error_message": None,
            "raw_metadata": {"demo": True, "author": "Demo Desk", "feed_url": "offline-demo", "tags": [category]},
        })
    return articles


def seed_demo_articles(repository) -> int:
    from app.metrics import DEMO_SEEDED

    stats = repository.save_articles(build_demo_articles())
    DEMO_SEEDED.inc(stats["inserted"])
    return stats["inserted"]
