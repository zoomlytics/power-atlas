# Seed Network Dataset for ACE Knowledge Graph from the Provided Snippet

## Scope and guardrails

This work converts the snippet into a **graph “seed” dataset** suitable for seeding and early visualization in a knowledge graph (ACE). The objective is **coverage and structure**, not adjudicating every narrative claim in the snippet.

Because the snippet contains **strong allegations and interpretive framing** (e.g., claims of “psyops,” “surveillance state targeting,” and assertions of intentional entrapment), the dataset is built around **verifiable, citable relationships** (roles, corporate links, patronage, published documents, and organizational affiliations). Content that is **defamatory, unverified, or not supported by high-quality evidence** is intentionally **not encoded as factual edges**. Where topics are inherently contested (for example, Cambridge Analytica’s “dirty tricks” claims), the dataset models only what is explicitly documented by reporting and investigations, and preserves **confidence levels** and **source provenance**. citeturn5news34turn5search0turn1news46

## Graph modeling decisions for ACE ingestion

The graph is modeled as a **property graph** with three concrete artifacts:

- **nodes.csv**: one row per node (person, organization, document/book, event, or concept).
- **edges.csv**: one row per directed edge, with a normalized predicate, optional time bounds, a confidence label, and evidence pointers.
- **sources.csv**: a compact catalog of canonical sources (URLs) keyed by `source_code`.

Key modeling choices:

- **Layers (clusters)**: nodes carry a `layer` field to support multi-layer visualization (e.g., “Modern activism,” “Alt-tech platforms,” “Data & influence industry,” “UK interfaith & metals,” “Historical Britain & Palestine,” “Theology & religious movements,” etc.).
- **Evidence plumbing**: each edge includes `evidence_codes` (e.g., `S010;S012`) that map to `sources.csv`. This keeps the dataset ingest-friendly while retaining traceability.
- **Confidence**: `high/medium/low` expresses how directly and consistently the relationship is supported by the cited sources (e.g., formal appointments = high; “successor/associated” corporate continuity = medium).
- **Temporal fields**: `start_date`/`end_date` are included where dates are central to interpretation (e.g., CEO changes, post-2018 shutdown, 2025 leadership succession). citeturn14news42turn14news46turn1news46

## Seed entities extracted and controlled expansion to about fifty nodes

The snippet’s named-entity “seeds” were normalized and expanded into a ~50-node starter network, keeping growth “within reason” by staying close to the snippet’s backbone:

- Modern activism cluster centered on entity["organization","Turning Point USA","u.s. conservative nonprofit"] and its close satellites entity["organization","Turning Point Action","u.s. 501c4 advocacy arm"] and entity["organization","Turning Point UK","uk political group 2019"], anchored by individuals including entity["people","Charlie Kirk","u.s. activist 1993-2025"], entity["people","Erika Kirk","tpusa ceo 2025"], entity["people","Candace Owens","u.s. commentator"], and entity["people","George Farmer","parler ceo british businessman"]. citeturn12search12turn14news42turn14news46turn2search2turn2search9  
- Alt-tech / platform cluster centered on entity["company","Parler","alt-tech social network"] and corporate/leadership links including entity["company","Parlement Technologies","parler parent company"] and financiers such as entity["people","Rebekah Mercer","u.s. political donor"] and entity["people","Dan Bongino","u.s. commentator"]. citeturn1search1turn1search2turn2search31turn6search3turn1news43  
- Data/behavioral influence cluster centered on entity["company","Cambridge Analytica","data firm 2013-2018"] and entity["company","SCL Group","uk strategic comms firm"], with precursor naming entity["organization","Behavioural Dynamics Institute","scl original name"] and key executives entity["people","Nigel Oakes","scl founder"] and entity["people","Alexander Nix","cambridge analytica ceo"], plus the media/political bridge via entity["people","Steve Bannon","political strategist"]. citeturn1search0turn1search4turn4search2turn5search3turn5news34  
- UK interfaith & metals cluster centered on entity["people","Michael Farmer, Baron Farmer","uk life peer metals trader"], institutions including entity["organization","House of Lords","uk parliament upper house"], entity["organization","Council of Christians and Jews","interfaith charity uk"] (with patronage by entity["people","King Charles III","uk monarch"]), and markets/firms including entity["organization","London Metal Exchange","metals futures exchange uk"] and entity["company","Red Kite Group","metals investment firm"]. citeturn9search2turn3search3turn10search4turn10news32  
- Publishing / historical Britain–Palestine thread centered on entity["company","Oxford University Press","publisher oxford"] and entity["book","Scofield Reference Bible","study bible 1909"] (edited by entity["people","C. I. Scofield","bible editor"]), and the imperial-diplomatic documents and institutions surrounding the Mandate-era baseline, including entity["organization","League of Nations","international organization 1920-1946"], alongside the publishing house entity["company","Pergamon Press","academic publisher oxford"] built by entity["people","Robert Maxwell","media proprietor 1923-1991"]. citeturn4search9turn3search6turn3search8turn4search0  
- Conservative policy/media ecosystem nodes were included because the snippet explicitly names them: entity["organization","Breitbart News","conservative news site"] and entity["organization","The Heritage Foundation","think tank washington dc"]. citeturn11search3turn15search6

image_group{"layout":"carousel","aspect_ratio":"16:9","query":["Balfour Declaration 1917 letter image","Scofield Reference Bible 1917 edition cover","Cambridge Analytica logo","Parler logo"],"num_per_query":1}

## Network highlights grounded in current and archival sources

The dataset encodes several high-signal “bridges” implied by the snippet, but only where sources support the links:

The **Turning Point governance spine** is anchored by the documented fact pattern that Charlie Kirk founded TPUSA in 2012 and later founded TPAction in 2019; he was killed on September 10, 2025, and TPUSA’s board appointed Erika Kirk as CEO on September 18, 2025. citeturn14news42turn14news46turn14search0turn12search12

The **Parler–Mercer–UK bridge** is modeled through George Farmer’s documented roles (chairing Turning Point UK in 2019 and later leading Parler as CEO), plus Parler’s described positioning as an “alt-tech” platform and the widely reported Mercer-family involvement in financing and governance. citeturn2search1turn6search3turn7search1turn1news43turn15search3

The **SCL/Cambridge Analytica commercial structure** is represented as a corporate chain (SCL Group → Cambridge Analytica), including the founding lineage (“Behavioural Dynamics Institute” naming at origin) and key individuals (Nigel Oakes as founder; Alexander Nix as CEO; Steve Bannon as an executive figure described as tied to the firm). The dataset also includes a central event node for the 2018 Facebook/Cambridge Analytica scandal that precipitated shutdown/insolvency. citeturn1search0turn1search4turn4search2turn5news34turn1news46

The **UK interfaith + metals financing thread** is built from primary institutional records: Michael Farmer’s membership and roles (House of Lords; CCJ deputy chair) and the CCJ’s confirmation that King Charles became its patron in May 2024. It also includes Farmer’s long-documented identity as a metals trader and co-founder of Red Kite, tied to London’s metals ecosystem. citeturn9search2turn3search3turn10search4turn10news32

The **historical publishing and theology strand** is intentionally separate as a contextual layer: Oxford University Press publishing the Scofield Reference Bible (1909; revised 1917) and the Bible’s association with dispensationalist interpretive frameworks (encoded as concept-to-concept influence) are represented as context—not as proof of any modern operational coordination. citeturn4search9turn4search1turn8search16

## ACE-ready dataset artifacts

The dataset below is structured so that `edges.csv.evidence_codes` points to `sources.csv.source_code`. This keeps the graph ingest-friendly while preserving provenance.

```csv
node_id,name,type,layer,aliases,description
ORG_TPUSA,Turning Point USA,Organization,Modern activism,TPUSA,"U.S. conservative nonprofit focused on high school and college campuses, founded in 2012."
ORG_TPUK,Turning Point UK,Organization,Modern activism,TPUK,Short-lived UK offshoot launched in 2019.
PER_CHARLIE_KIRK,Charlie Kirk,Person,Modern activism,,U.S. conservative activist; co-founder and longtime leader of Turning Point USA; killed Sept 10, 2025.
PER_ERIKA_KIRK,Erika Kirk,Person,Modern activism,Erika Frantzve Kirk;Erika Frantzve,"Entrepreneur; widow of Charlie Kirk; appointed CEO/Chair of Turning Point USA in Sept 2025."
PER_CANDACE_OWENS,Candace Owens,Person,Modern activism,,U.S. political commentator; served as communications director at Turning Point USA (2017–2019).
PER_GEORGE_FARMER,George Farmer,Person,Alt-tech platforms,,British businessman; chaired Turning Point UK and later led Parler as CEO.
PER_MICHAEL_FARMER,"Michael Farmer, Baron Farmer",Person,UK interfaith & metals,Lord Farmer,"British metals trader and life peer; Conservative Party treasurer; deputy chair of CCJ; father of George Farmer."
ORG_CCJ,Council of Christians and Jews,Organization,UK interfaith & metals,CCJ,"UK interfaith charity/organization founded in 1942 promoting Christian–Jewish dialogue; royal patronage held by the monarch."
PER_KING_CHARLES,King Charles III,Person,UK interfaith & metals,,Monarch of the UK; became CCJ patron in May 2024.
ORG_HOUSE_OF_LORDS,House of Lords,Organization,UK interfaith & metals,,Upper chamber of the UK Parliament; Michael Farmer is a life peer member.
ORG_CONSERVATIVE_PARTY_UK,Conservative Party (UK),Organization,UK interfaith & metals,,Major UK political party; Michael Farmer served as party treasurer/co-treasurer.
ORG_LME,London Metal Exchange,Organization,UK interfaith & metals,LME,"London Metal Exchange, major industrial metals futures/forwards exchange."
ORG_REDKITE,Red Kite Group,Organization,UK interfaith & metals,,Metals trading/investment group co-founded by Michael Farmer and others; known for commodities/metal markets.
ORG_PARLER,Parler,Organization,Alt-tech platforms,,U.S. 'alt-tech' social networking service launched in 2018; underwent ownership changes and shutdown/relaunch cycles.
ORG_PARLEMENT_TECH,Parlement Technologies,Organization,Alt-tech platforms,Parlement,Former parent company of Parler (corporate structure used post-2021).
PER_DAN_BONGINO,Dan Bongino,Person,Alt-tech platforms,,U.S. conservative commentator who publicly announced an ownership stake in Parler.
PER_REBEKAH_MERCER,Rebekah Mercer,Person,Alt-tech platforms,,American political donor; funded/co-founded Parler; director of Mercer Family Foundation; trustee of Heritage Foundation.
PER_ROBERT_MERCER,Robert Mercer,Person,Finance & political funding,,Hedge fund manager/computer scientist; former co-CEO of Renaissance Technologies; major conservative donor and investor in CA; donor to Heritage.
ORG_RENTECH,Renaissance Technologies,Organization,Finance & political funding,RenTec;RenTech,"Quantitative hedge fund founded by Jim Simons; developed Medallion Fund; Mercer served as co-CEO."
ORG_CAMBRIDGE_ANALYTICA,Cambridge Analytica,Organization,Data & influence industry,,British political consulting/data firm (2013–2018) tied to Facebook data scandal; subsidiary of SCL Group.
ORG_SCL_GROUP,SCL Group,Organization,Data & influence industry,Strategic Communication Laboratories;SCL,"British behavioural research/strategic communications company (1990–2018); parent of Cambridge Analytica."
ORG_BDI,Behavioural Dynamics Institute,Organization,Data & influence industry,BDI,Behavioural Dynamics Institute—name used at SCL's founding (1990) per multiple sources.
PER_NIGEL_OAKES,Nigel Oakes,Person,Data & influence industry,,British businessman; founder of SCL Group.
PER_ALEXANDER_NIX,Alexander Nix,Person,Data & influence industry,,Former CEO of Cambridge Analytica.
ORG_EMERDATA,Emerdata,Organization,Data & influence industry,,"Company discussed as potential successor entity to Cambridge Analytica/SCL after 2018 wind-down."
ORG_META,Meta Platforms,Organization,Data & influence industry,,Parent company of Facebook; platform at center of CA data misuse scandal.
EVT_CA_SCANDAL,Facebook-Cambridge Analytica data scandal,Event,Data & influence industry,,2018 scandal regarding misuse of Facebook user data involving Cambridge Analytica/SCL.
EVT_JAN6,January 6 United States Capitol attack,Event,US politics & extremism online,,Attack on the U.S. Capitol on Jan 6, 2021 aimed at stopping election certification.
CON_QANON,QAnon,Concept,US politics & extremism online,,Conspiracy theory movement originating in 2017 centered on anonymous 'Q' posts.
DOC_SCOFIELD_BIBLE,Scofield Reference Bible,Document,Theology & religious movements,Scofield Bible;Scofield Reference Bible,"Influential study Bible first published 1909 (revised 1917) by Oxford University Press."
PER_CYRUS_SCOFIELD,C. I. Scofield,Person,Theology & religious movements,C. I. Scofield;Cyrus Ingerson Scofield,American theologian/Bible editor associated with the Scofield Reference Bible.
ORG_OXFORD_UP,Oxford University Press,Organization,Publishing & institutions,OUP,Oxford University Press; publisher of the Scofield Reference Bible editions.
CON_DISPENSATIONALISM,Dispensationalism,Concept,Theology & religious movements,,Theological framework developed in 19th century; influential in some evangelical circles.
CON_CHRISTIAN_ZIONISM,Christian Zionism,Concept,Theology & religious movements,,Christian movement supporting Zionism/Israel often on theological grounds.
CON_ZIONISM,Zionism,Concept,Theology & political movements,,Jewish national movement supporting a homeland/state in Palestine/Israel; emerged late 19th century.
DOC_BALFOUR,Balfour Declaration,Document,Historical Britain & Palestine,Balfour Declaration letter,1917 letter announcing British support for a 'national home for the Jewish people' in Palestine.
PER_ARTHUR_BALFOUR,Arthur Balfour,Person,Historical Britain & Palestine,Arthur James Balfour,UK Foreign Secretary who signed the 1917 Balfour Declaration letter.
PER_WALTER_ROTHSCHILD,Walter Rothschild,Person,Historical Britain & Palestine,Lionel Walter Rothschild,British Jewish community leader; addressee of the Balfour Declaration letter.
DOC_MANDATE_PALESTINE,Mandate for Palestine,Document,Historical Britain & Palestine,League of Nations Mandate for Palestine,"League of Nations mandate assigning Britain administrative authority in Palestine; approved 1922."
ORG_LEAGUE_NATIONS,League of Nations,Organization,Historical Britain & Palestine,,International organization (1920–1946) that approved the Mandate for Palestine.
ORG_PERGAMON,Pergamon Press,Organization,Publishing & institutions,Pergamon Press Ltd.,"Oxford-based scientific/medical publishing house built by Robert Maxwell (renamed Pergamon Press in 1951)."
PER_ROBERT_MAXWELL,Robert Maxwell,Person,Publishing & institutions,Ian Robert Maxwell,"Media proprietor/publisher; built Pergamon Press into major academic publisher."
ORG_BREITBART,Breitbart News,Organization,Media & political ecosystem,,Conservative news and opinion website founded in 2007; later led by Steve Bannon as executive chairman.
PER_STEVE_BANNON,Steve Bannon,Person,Media & political ecosystem,,U.S. political strategist/media executive; executive chair at Breitbart; former VP at Cambridge Analytica.
ORG_HERITAGE,The Heritage Foundation,Organization,Policy/think tanks,,"U.S. conservative think tank founded in 1973; governed by Board of Trustees including Rebekah Mercer."
PER_LORD_IVAR,Lord Ivar Mountbatten,Person,Data & influence industry,Ivar Mountbatten,British aristocrat; former director of SCL Group (parent of Cambridge Analytica).
ORG_TPACTION,Turning Point Action,Organization,Modern activism,TPAction,Political advocacy arm (501(c)(4)) founded in 2019 as sister organization to Turning Point USA.
PER_BILL_MONTGOMERY,Bill Montgomery,Person,Modern activism,,Conservative activist and marketing entrepreneur; co-founder of Turning Point USA; died in 2020.
ORG_PARLEMENT_TECH,Parlement Technologies,Organization,Alt-tech platforms,Parlement,Former parent company of Parler (corporate structure used post-2021).
PER_JOHN_MATZE,John Matze,Person,Alt-tech platforms,,Parler co-founder and early CEO who was later terminated by the board.
CON_EVANGELICALISM,Evangelicalism,Concept,Theology & religious movements,,Broad Protestant movement emphasizing conversion, Scripture, and evangelism.
```

```csv
edge_id,source_id,target_id,predicate,start_date,end_date,confidence,evidence_codes,note
E1,PER_CHARLIE_KIRK,ORG_TPUSA,COFOUNDED,2012-06,2025-09-10,high,S001;S003;S005,Co-founded and led until death
E2,PER_BILL_MONTGOMERY,ORG_TPUSA,COFOUNDED,2012-06,2020-07,high,S005,Co-founder; served as secretary/treasurer until 2020 per wiki; died 2020
E3,PER_ERIKA_KIRK,ORG_TPUSA,CEO_OF,2025-09-18,,high,S004,Appointed CEO/Chair after Kirk's death
E4,PER_CANDACE_OWENS,ORG_TPUSA,HELD_ROLE,2017-11,2019-05,high,S006,Communications director / director of urban engagement
E5,ORG_TPUK,ORG_TPUSA,AFFILIATE_OF,2019-02,,high,S007;S008,UK offshoot
E6,PER_GEORGE_FARMER,ORG_TPUK,CHAIR_OF,2019-02,2019-04,high,S007,Chairman until Apr 2019
E7,PER_GEORGE_FARMER,ORG_PARLER,CEO_OF,2021-05,2023-04,high,S010,CEO of Parler
E8,PER_GEORGE_FARMER,ORG_PARLEMENT_TECH,CEO_OF,2021-05,2023-04,high,S009,CEO of parent company Parlement Technologies
E9,ORG_PARLEMENT_TECH,ORG_PARLER,PARENT_COMPANY_OF,,,high,S010,Parler parent company
E10,ORG_TPACTION,ORG_TPUSA,AFFILIATE_OF,2019,,high,S005,Sister political arm
E11,PER_CHARLIE_KIRK,ORG_TPACTION,FOUNDED,2019,,high,S003;S005,Founded 2019
E12,EVT_JAN6,ORG_TPACTION,ASSOCIATED_WITH,,,medium,S004;S041,TPAction activities connected to Jan 6 rally planning/transport per reporting
E13,PER_REBEKAH_MERCER,ORG_PARLER,COFOUNDED_OR_FUNDED,2018,,high,S011,Funded and co-founded per sources
E14,PER_DAN_BONGINO,ORG_PARLER,INVESTED_IN,2020-06,,medium,S012,Announced ownership stake
E15,PER_JOHN_MATZE,ORG_PARLER,FOUNDED,2018-08,,high,S010,Co-founder/CEO at launch
E16,PER_ROBERT_MERCER,ORG_PARLER,MAJOR_BACKER_OF,2018,,high,S010,Mercer family financial backing widely reported
E17,PER_ROBERT_MERCER,PER_REBEKAH_MERCER,PARENT_OF,,,high,S013,Father-daughter
E18,PER_ROBERT_MERCER,ORG_RENTECH,EXECUTIVE_ROLE,2010,2017,high,S013;S014,Co-CEO of Renaissance (dates approximate)
E19,ORG_CAMBRIDGE_ANALYTICA,ORG_SCL_GROUP,SUBSIDIARY_OF,2013,2018-05-01,high,S015;S016,CA subsidiary of SCL
E20,PER_NIGEL_OAKES,ORG_SCL_GROUP,FOUNDED,1990,,high,S016;S032,Founded SCL predecessor/BDI and SCL Group
E21,ORG_BDI,ORG_SCL_GROUP,FORMER_NAME_OR_PREDECESSOR_OF,1990,2005,high,S016,Founded as Behavioural Dynamics Institute
E22,PER_ALEXANDER_NIX,ORG_CAMBRIDGE_ANALYTICA,CEO_OF,2015,2018,high,S015;S033,CEO
E23,PER_STEVE_BANNON,ORG_CAMBRIDGE_ANALYTICA,EXECUTIVE_ROLE,2013,2017,high,S015;S031,Vice president / executive role
E24,PER_ROBERT_MERCER,ORG_CAMBRIDGE_ANALYTICA,INVESTED_IN,2013,2018,high,S013;S015,Major investor
E25,PER_REBEKAH_MERCER,ORG_CAMBRIDGE_ANALYTICA,INVESTED_IN,2013,2018,high,S015,Investor/director per sources
E26,ORG_SCL_GROUP,ORG_CAMBRIDGE_ANALYTICA,PARENT_COMPANY_OF,2013,2018,high,S015;S016,Parent company relationship
E27,ORG_EMERDATA,ORG_CAMBRIDGE_ANALYTICA,SUCCESSOR_OR_ASSOCIATED_WITH,2017,,medium,S016;S035,Emerdata created by people involved; discussed as successor
E28,PER_REBEKAH_MERCER,ORG_EMERDATA,BOARD_MEMBER_OF,2018,,medium,S016,Rebekah Mercer on board per SCL article
E29,PER_LORD_IVAR,ORG_SCL_GROUP,DIRECTOR_OF,,,medium,S045,Former director
E30,EVT_CA_SCANDAL,ORG_META,INVOLVED_PLATFORM,2018-03,2018-05,high,S034;S035,Facebook data misuse scandal
E31,EVT_CA_SCANDAL,ORG_CAMBRIDGE_ANALYTICA,INVOLVED_ORG,2018-03,2018-05,high,S035,CA at center of scandal
E32,EVT_CA_SCANDAL,ORG_SCL_GROUP,INVOLVED_ORG,2018-03,2018-05,high,S035,SCL impacted/closed amid scandal
E33,CON_QANON,EVT_JAN6,ASSOCIATED_WITH,,,medium,S037;S041,QAnon presence among Jan 6 participants
E34,CON_QANON,ORG_PARLER,CONTENT_COMMUNITY_ON,,,medium,S036;S010,Parler hosted QAnon-related content (context)
E35,CON_EVANGELICALISM,CON_CHRISTIAN_ZIONISM,RELATED_TO,,,medium,S038;S039,Christian Zionism often within evangelical context
E36,CON_DISPENSATIONALISM,CON_CHRISTIAN_ZIONISM,INFLUENCED,,,medium,S039,Dispensationalism has lasting impact on Christian Zionism
E37,CON_CHRISTIAN_ZIONISM,CON_ZIONISM,RELIGIOUS_SUPPORT_FOR,,,medium,S039,Christian Zionism is Christian support for Zionism/Israel
E38,PER_CYRUS_SCOFIELD,DOC_SCOFIELD_BIBLE,EDITED,1909,1917,high,S021;S022,Editor; editions
E39,ORG_OXFORD_UP,DOC_SCOFIELD_BIBLE,PUBLISHED,1909,1917,high,S021;S022,Published by OUP
E40,DOC_SCOFIELD_BIBLE,CON_DISPENSATIONALISM,POPULARIZED,1909,,medium,S021;S039,Scofield Bible popularized dispensationalism
E41,PER_ARTHUR_BALFOUR,DOC_BALFOUR,AUTHORED,1917-11-02,,high,S023,Authored declaration letter
E42,DOC_BALFOUR,PER_WALTER_ROTHSCHILD,ADDRESSED_TO,1917-11-02,,high,S023;S024,Letter addressed to Lord Rothschild
E43,DOC_MANDATE_PALESTINE,ORG_LEAGUE_NATIONS,APPROVED_BY,1922-07-24,,high,S025,Mandate approved by League of Nations
E44,DOC_MANDATE_PALESTINE,DOC_BALFOUR,INCORPORATED_PRINCIPLES_OF,1922,,medium,S025;S026,Mandate built on Balfour principles
E45,PER_ROBERT_MAXWELL,ORG_PERGAMON,FOUNDED_OR_LED,1951,,high,S027;S028;S029,Renamed/led Pergamon Press
E46,ORG_PERGAMON,PER_ROBERT_MAXWELL,FOUNDED_BY,1951,,high,S027;S028,Founded/renamed by Maxwell
E47,PER_STEVE_BANNON,ORG_BREITBART,EXECUTIVE_ROLE,2012,2016,medium,S030;S031,Executive chairman after Andrew Breitbart's death
E48,PER_REBEKAH_MERCER,ORG_BREITBART,FUNDED_OR_OWNED_STAKE,2012,,medium,S013;S015,Mercer family funding/ownership stake reported
E49,PER_REBEKAH_MERCER,ORG_HERITAGE,TRUSTEE_OF,2014,,high,S042;S043,Heritage trustee/board member
E50,PER_ROBERT_MERCER,ORG_HERITAGE,DONATED_TO,,,medium,S013,Donations listed among recipients
E51,PER_MICHAEL_FARMER,ORG_HOUSE_OF_LORDS,MEMBER_OF,2014-09-05,,high,S017;S044,Life peer; sits in House of Lords
E52,PER_MICHAEL_FARMER,ORG_CCJ,DEPUTY_CHAIR_OF,2016,,high,S017;S019;S044,Deputy Chair / Vice Chair per sources
E53,PER_KING_CHARLES,ORG_CCJ,PATRON_OF,2024-05-20,,high,S018,Royal patronage confirmed May 2024
E54,PER_MICHAEL_FARMER,ORG_CONSERVATIVE_PARTY_UK,TREASURER_OF,2011,2015,high,S020;S044,Co-treasurer/treasurer role
E55,PER_MICHAEL_FARMER,ORG_REDKITE,COFOUNDED,2004,,high,S020;S044,Co-founded Red Kite Group
E56,PER_MICHAEL_FARMER,ORG_LME,ASSOCIATED_WITH,,,medium,S044,Career as metals trader tied to LME vicinity/market
```

```csv
source_code,title,url
S001,Encyclopaedia Britannica: Turning Point USA,https://www.britannica.com/topic/Turning-Point-USA
S002,Turning Point USA official site,https://tpusa.com/
S003,"Reuters: Charlie Kirk death & TPUSA/TPAction background (Sep 10, 2025)",https://www.reuters.com/world/us/right-wing-activist-charlie-kirk-dead-31-played-key-role-trumps-2024-victory-2025-09-10/
S004,"Washington Post: Erika Kirk appointed to lead TPUSA (Sep 18, 2025)",https://www.washingtonpost.com/politics/2025/09/18/charlie-erika-kirk-turning-point/
S005,Wikipedia: Turning Point USA,https://en.wikipedia.org/wiki/Turning_Point_USA
S006,Wikipedia: Candace Owens,https://en.wikipedia.org/wiki/Candace_Owens
S007,Wikipedia: Turning Point UK,https://en.wikipedia.org/wiki/Turning_Point_UK
S008,"The Independent: Turning Point UK launch/support (Feb 4, 2019)",https://www.independent.co.uk/news/uk/home-news/turning-point-uk-jacob-rees-mogg-conservative-right-wing-group-launch-tory-a8762351.html
S009,Wikipedia: George Farmer (businessman),https://en.wikipedia.org/wiki/George_Farmer_(businessman)
S010,Wikipedia: Parler,https://en.wikipedia.org/wiki/Parler
S011,Wikipedia: Rebekah Mercer,https://en.wikipedia.org/wiki/Rebekah_Mercer
S012,"Business Insider: Parler investors incl. Dan Bongino (Nov 16, 2020)",https://www.businessinsider.com/parlers-investors-include-a-big-angel-investor-and-a-pro-trump-pundit-2020-11
S013,Wikipedia: Robert Mercer,https://en.wikipedia.org/wiki/Robert_Mercer
S014,Wikipedia: Renaissance Technologies,https://en.wikipedia.org/wiki/Renaissance_Technologies
S015,Wikipedia: Cambridge Analytica,https://en.wikipedia.org/wiki/Cambridge_Analytica
S016,Wikipedia: SCL Group,https://en.wikipedia.org/wiki/SCL_Group
S017,UK Parliament: Lord Farmer experience page,https://members.parliament.uk/member/4321/experience
S018,"Council of Christians and Jews: King Charles becomes Patron (May 2024)",https://ccj.org.uk/news/king-patronage
S019,Charity Commission: Council of Christians and Jews registration,https://register-of-charities.charitycommission.gov.uk/en/charity-search/-/charity-details/238005
S020,"Reuters: From 'Mr Copper' to Lord Farmer (Aug 10, 2014)",https://www.reuters.com/article/world/us/from-mr-copper-to-lord-farmer-metals-trading-legend-becomes-british-peer-idUSKBN0GA0XT/
S021,Wikipedia: Scofield Reference Bible,https://en.wikipedia.org/wiki/Scofield_Reference_Bible
S022,"Museum of the Bible artifact note: Scofield Reference Bible editions",https://collections.museumofthebible.org/artifacts/14837-scofield-reference-bible-second-edition
S023,Yale Avalon Project: Balfour Declaration text,https://avalon.law.yale.edu/20th_century/balfour.asp
S024,"Rothschild Archive: Walter Rothschild and the Balfour Declaration",https://www.rothschildarchive.org/family/family_interests/walter_rothschild_and_the_balfour_declaration
S025,UN: Mandate for Palestine document,https://www.un.org/unispal/document/auto-insert-201057/
S026,"Hansard (UK Parliament): Palestine Mandate debate (Jun 21, 1922)",https://hansard.parliament.uk/lords/1922-06-21/debates/4a00f5d1-4cca-41fd-8d0b-2ab961c1e70e/PalestineMandate
S027,Wikipedia: Pergamon Press,https://en.wikipedia.org/wiki/Pergamon_Press
S028,Encyclopaedia Britannica: Pergamon Press Ltd.,https://www.britannica.com/topic/Pergamon-Press-Ltd
S029,Wikipedia: Robert Maxwell,https://en.wikipedia.org/wiki/Robert_Maxwell
S030,Wikipedia: Breitbart News,https://en.wikipedia.org/wiki/Breitbart_News
S031,Wikipedia: Steve Bannon,https://en.wikipedia.org/wiki/Steve_Bannon
S032,Wikipedia: Nigel Oakes,https://en.wikipedia.org/wiki/Nigel_Oakes
S033,Wikipedia: Alexander Nix,https://en.wikipedia.org/wiki/Alexander_Nix
S034,"Wired: Cambridge Analytica execs caught discussing unethical tactics (Mar 19, 2018)",https://www.wired.com/story/cambridge-analytica-execs-caught-discussing-extortion-and-fake-news/
S035,"Wired: Cambridge Analytica shuts down amid Facebook crisis (May 2, 2018)",https://www.wired.com/story/cambridge-analytica-shuts-down-offices-facebook-crisis/
S036,"New America: Parler and the Road to the Capitol Attack (2022)",https://www.newamerica.org/future-frontlines/reports/parler-and-the-road-to-the-capitol-attack/
S037,Britannica: QAnon,https://www.britannica.com/topic/QAnon
S038,Britannica: Evangelical church definition,https://www.britannica.com/topic/Evangelical-church-Protestantism
S039,"Cambridge repository: Dispensationalism impact on Christian Zionism (Durbin pdf)",https://www.repository.cam.ac.uk/bitstreams/95318571-eec6-401a-a144-081ba5d6d657/download
S040,Wikipedia: QAnon,https://en.wikipedia.org/wiki/QAnon
S041,Wikipedia: January 6 United States Capitol attack,https://en.wikipedia.org/wiki/January_6_United_States_Capitol_attack
S042,Heritage Foundation: Rebekah Mercer staff page,https://www.heritage.org/staff/rebekah-mercer
S043,Heritage Foundation: Board of Trustees,https://www.heritage.org/board-trustees
S044,"Wikipedia: Michael Farmer, Baron Farmer",https://en.wikipedia.org/wiki/Michael_Farmer,_Baron_Farmer
S045,Wikipedia: Lord Ivar Mountbatten,https://en.wikipedia.org/wiki/Lord_Ivar_Mountbatten
```

## Data quality notes and exclusions

Several assertions in the snippet are **not represented as factual edges**, including claims that evangelicalism is a “military psyop,” that QAnon was “planted,” or that specific individuals are “feds.” Those claims are interpretive and/or defamatory and cannot be grounded as facts from credible sources.

Where sensitive topics *are* represented (e.g., Cambridge Analytica “dirty tricks” content), the dataset does so only in the narrow, source-supported manner: it includes the scandal event node and the corporate/personnel structure linked to it; and it relies on contemporary reporting about what executives were recorded saying and the firm’s subsequent collapse. citeturn5news34turn1news46turn5search0