"""Natural-conversation regression set (2026-10-02).

Hundreds of realistic customer messages and multi-turn journeys -- Zambian
English, text-speak, typos, greetings around requests, follow-ups, lead-form
answers as people really type them -- each with the outcomes a customer would
accept. Built by probing the bot until it broke, then fixing it; this file
keeps those fixes from regressing. An expectation is an intent name,
"action:<prefix>", "text:<substring>", "flow:<name>", a callable, or a tuple
of acceptable alternatives. Not held-out data: the E3 gates stay the
measure of the matcher itself.
"""
import pytest



def _ok(expect, b):
    meta = b.last[1]
    got_intent, got_action = meta.get("intent") or meta.get("action"), meta.get("action") or ""
    for e in expect if isinstance(expect, (set, tuple, list)) else [expect]:
        if callable(e) and e(b):
            return True
        if isinstance(e, str) and (
            (e.startswith("action:") and got_action.startswith(e[7:]))
            or (e.startswith("text:") and e[5:].lower() in b.text.lower())
            or (e.startswith("flow:") and b.session.active_flow == e[5:])
            or e == got_intent
        ):
            return True
    return False


# --- round 1: single messages
DYM = "action:did_you_mean"
LEAD = "flow:lead"
FRAUD = ("flow:fraud", "action:urgent")
OOS = ("out_of_scope", "action:fallback", DYM)
GREET = ("greeting", "how_are_you")
SINGLES = [
 # --- greetings & small talk (Zambian English, typos, combos)
 ("hello", GREET), ("Hello!", GREET), ("hi there", GREET), ("hey", GREET), ("helo", GREET), ("hie", GREET),
 ("good morning", GREET), ("Good morning!", GREET), ("good afternoon sir", GREET), ("good evening madam", GREET),
 ("hi how are you", GREET), ("hello, how are you?", GREET), ("good morning how are you", GREET),
 ("hey bot", GREET), ("hi AB bank", GREET), ("yo", GREET), ("howzit", GREET), ("morning!", GREET),
 ("muli bwanji", GREET), ("mwabuka bwanji", GREET), ("hello hello", GREET),
 ("how are you?", "how_are_you"), ("how are you doing today", "how_are_you"), ("hows your day going?", "how_are_you"),
 ("i am fine thanks", "small_talk_fine"), ("im good and you", ("small_talk_fine","thanks_goodbye")), ("fine", "small_talk_fine"),
 ("thank you", "thanks_goodbye"), ("thanks a lot!", "thanks_goodbye"), ("thank you so much", "thanks_goodbye"),
 ("ok thanks bye", "thanks_goodbye"), ("bye", "thanks_goodbye"), ("goodbye", "thanks_goodbye"), ("good night", "thanks_goodbye"),
 ("see you later", "thanks_goodbye"), ("cheers", "thanks_goodbye"), ("zikomo", "thanks_goodbye"), ("natotela", "thanks_goodbye"),
 ("ok", "acknowledgement"), ("okay", "acknowledgement"), ("alright", "acknowledgement"), ("cool", "acknowledgement"),
 ("ok noted", ("acknowledgement","thanks_goodbye")), ("i see", "acknowledgement"), ("great", "acknowledgement"),
 ("what is your name", "bot_name"), ("whats ur name", "bot_name"), ("who are you", ("bot_capabilities","bot_name")),
 ("are you a robot", "bot_capabilities"), ("am i talking to a real person", "bot_capabilities"), ("are you human?", "bot_capabilities"),
 ("what can you do", "bot_capabilities"), ("what can you help me with", "bot_capabilities"), ("help", "action:help"),
 ("i need help", ("bot_capabilities","action:help","human_handoff")), ("can you help me", ("bot_capabilities","action:help")),
 ("please help me", ("bot_capabilities","action:help")), ("hello i need help", ("bot_capabilities","greeting","action:help")),
 ("you are very helpful", "compliment"), ("good job", "compliment"), ("lol", "compliment"), ("haha nice", ("compliment","acknowledgement")),
 ("nice to meet you", "nice_to_meet_you"), ("are you there", "are_you_there"), ("hello?", ("are_you_there","greeting")),
 ("anyone there?", "are_you_there"), ("sorry", ("acknowledgement","action:repeat","action:fallback","action:clarify")),
 ("you are useless", ("action:frustration","abuse")), ("this bot is stupid", ("action:frustration","abuse")),
 # --- accounts
 ("i want to open an account", ("account_types_overview","account_opening_how")),
 ("how do i open an account", ("account_opening_how","account_opening_requirements")),
 ("open account", ("account_opening_how","account_types_overview")),
 ("what accounts do you have", "account_types_overview"), ("types of accounts", "account_types_overview"),
 ("accounts", "account_types_overview"), ("account", ("account_types_overview", DYM)),
 ("savings account", "savings_account"), ("i want to save money", ("savings_options","savings_account","savings_plan_account")),
 ("savings", ("savings_options","savings_account")), ("what savings accounts do you have", ("savings_options","savings_account")),
 ("tell me about tamanga", "current_account"), ("tamanga account", "current_account"), ("current account", "current_account"),
 ("tamanga plus", "tamanga_plus_account"), ("whats the difference between tamanga and tamanga plus", ("tamanga_plus_account","current_account")),
 ("business account", "business_account"), ("account for my company", "business_account"), ("mukula plus", "business_account"),
 ("account for my church", "business_account"), ("what do i need to open a business account", "business_account_requirements"),
 ("savings plan", "savings_plan_account"), ("account for my child", "kids_savings_account"), ("kids account", "kids_savings_account"),
 ("fixed deposit", "term_deposit_account"), ("term deposit", "term_deposit_account"), ("i want to invest", "invest_overview"),
 ("investments", "invest_overview"), ("where can i invest my money", ("invest_overview","term_deposit_account")),
 ("best interest rate for savings", ("term_deposit_account","savings_plan_account","savings_options","savings_account",DYM)),
 ("joint account", "joint_account"), ("can foreigners open an account", "foreign_national_account"),
 ("i am not zambian can i open an account", "foreign_national_account"),
 ("what documents do i need to open an account", "account_opening_requirements"), ("requirements for opening account", "account_opening_requirements"),
 ("can i open an account online", "account_opening_how"), ("bank statement", "bank_statement_request"),
 ("how do i get my statement", "bank_statement_request"), ("my account is dormant", "account_reactivation"),
 ("swift code", "sort_swift_code"), ("what is your sort code", "sort_swift_code"),
 # --- loans
 ("i want a loan", ("loans_overview","msme_loan","loan_apply_how",DYM)), ("loan", "loans_overview"), ("loans", "loans_overview"),
 ("i need money for my business", ("msme_loan","loans_overview","business_loan_options","micro_loan","sme_loan",DYM)),
 ("business loan", ("msme_loan","business_loan_options")), ("micro loan", "micro_loan"), ("sme loan", ("sme_loan","msme_loan")),
 ("loan for a motorbike", "trader_mobility_loan"), ("i want to buy a tricycle for my business", "trader_mobility_loan"),
 ("overdraft", "sme_overdraft"), ("personal loan", "personal_loan"), ("i am a civil servant can i get a loan", "personal_loan"),
 ("loan for farmers", "agri_loan"), ("what do i need to get a loan", "loan_requirements"),
 ("how do i apply for a loan", "loan_apply_how"), ("what is a guarantor", "guarantor_definition"), ("what is collateral", "collateral_definition"),
 ("loan interest rate", ("msme_loan","personal_loan","loans_overview",DYM)), ("how much can i borrow", ("personal_loan","msme_loan","loans_overview",DYM)),
 ("school fees loan", ("personal_loan",DYM,"out_of_scope")),
 # --- etumba & digital
 ("what is etumba", "etumba_what_is"), ("etumba", "etumba_what_is"), ("e-tumba", "etumba_what_is"), ("how do i register for etumba", "etumba_register"),
 ("etumba app", ("etumba_register","etumba_what_is")), ("*888#", "etumba_ussd"), ("how to check etumba balance", ("etumba_balance_check","etumba_ussd")),
 ("send money from etumba to airtel money", "etumba_transfer_mobile_money"), ("how to withdraw from etumba", "etumba_cash_in_out"),
 ("zesco token", "zesco_token"), ("i sent money to the wrong number", ("etumba_reversal","action:urgent")), ("yaka savings", "yaka_savings"),
 ("etumba charges", "etumba_fees"), ("online banking", "online_banking"), ("internet banking", "online_banking"),
 ("how do i register for internet banking", "online_banking"), ("mobile banking", "digital_banking"), ("digital banking", "digital_banking"),
 ("internet banking is not working", "technical_issue"), ("the app is not working", "technical_issue"),
 # --- fees, branches, contact
 ("what are your fees", "fees_charges"), ("bank charges", "fees_charges"), ("how much is tamanga per month", "fees_tamanga"),
 ("where is the kitwe branch", "branch_locator"), ("branch in ndola", "branch_locator"), ("where are you located", "branch_locator"),
 ("nearest branch", "branch_locator"), ("branches in lusaka", "branch_locator"), ("do you have a branch in chipata", "branch_locator"),
 ("do you have a branch in kabwe", ("branch_locator","text:kabwe")), ("where can i find an agent", "agent_locator"),
 ("etumba agents", "agent_locator"), ("opening hours", "opening_hours"), ("what time do you open", "opening_hours"),
 ("are you open on saturday", "opening_hours"), ("what time do you close today", "opening_hours"),
 ("contact details", "contact_details"), ("what is your phone number", "contact_details"), ("customer care number", ("contact_details","human_handoff")),
 ("email address", "contact_details"), ("whatsapp number", "contact_details"),
 ("i want to give feedback", "complaints_feedback"), ("i have a suggestion", "complaints_feedback"), ("i want to compliment your staff", "complaints_feedback"),
 # --- people & leads
 ("talk to a person", ("human_handoff", LEAD)), ("i want to speak to someone", ("human_handoff", LEAD)),
 ("call me back", ("human_handoff", LEAD, "request_callback")), ("can someone call me", ("human_handoff", LEAD)),
 ("please call me on 0977123456", ("human_handoff", LEAD)), ("i want to talk to an agent", ("human_handoff", LEAD)),
 ("i'm interested in the savings plan", ("savings_plan_account", LEAD)), ("sign me up for etumba", ("etumba_register","etumba_what_is",LEAD)),
 # --- urgent
 ("someone stole my card", FRAUD), ("i lost my card", FRAUD), ("my card was swallowed by the atm", (*FRAUD, "technical_issue", DYM)),
 ("money was taken from my account without my permission", FRAUD), ("i have been scammed", FRAUD), ("someone hacked my etumba", FRAUD),
 ("i want to make a complaint", ("flow:complaint","action:urgent")), ("i want to complain about poor service", ("flow:complaint","action:urgent")),
 ("i forgot my pin", ("credential_trouble",)), ("i forgot my password for online banking", "credential_trouble"),
 # --- out of scope
 ("what is the weather today", OOS), ("who won the football", OOS), ("tell me a joke", OOS), ("what is bitcoin", OOS),
 ("how do i apply for a passport", OOS), ("zesco load shedding schedule", OOS), ("what is the exchange rate", (*OOS,)),
 ("i want to buy airtime", ("etumba_what_is","etumba_ussd",*OOS)), ("asdfgh", ("action:fallback",)),
]

# --- round 2: fresh single messages
DYM = "action:did_you_mean"; LEAD = "flow:lead"; FRAUD = ("flow:fraud", "action:urgent")
OOS = ("out_of_scope", "action:fallback", DYM)
SINGLES2 = [
 # text-speak / typos / caps
 ("HELLO", ("greeting",)), ("HI THERE", ("greeting",)), ("gud morning", ("greeting",)), ("gd afternoon", ("greeting",)),
 ("hw r u", ("how_are_you",)), ("how r u doing", ("how_are_you",)), ("thnx", ("thanks_goodbye",)), ("tnx", ("thanks_goodbye",)),
 ("ok tnx", ("thanks_goodbye","acknowledgement")), ("ty", ("thanks_goodbye",)), ("thank u very much", ("thanks_goodbye",)),
 ("wat is etumba", ("etumba_what_is",)), ("hw do i open acc", ("account_opening_how","account_types_overview")),
 ("i wnt a savings acc", ("savings_account","savings_options")), ("savngs acount", ("savings_account","savings_options")),
 ("tamnga acount", ("current_account",)), ("WHERE IS YOUR LUSAKA BRANCH", ("branch_locator",)),
 ("open accnt pls", ("account_opening_how","account_types_overview")), ("loan pls", ("loans_overview",)),
 ("hw much is tamanga", ("fees_tamanga","current_account")), ("chipata branch?", ("branch_locator",)),
 ("ur opening hours", ("opening_hours",)), ("wats ur number", ("contact_details",)), ("pls call me", ("human_handoff", LEAD)),
 ("i need 2 talk to sum1", ("human_handoff", LEAD)), ("agent pls", ("human_handoff", LEAD)),
 # code-mixed / local
 ("muli shani", ("greeting","how_are_you")), ("ndifuna loan", ("loans_overview","msme_loan","loan_apply_how",DYM)), ("ndifuna kutsegula account", ("account_opening_how","account_types_overview",DYM)),
 ("zikomo kwambiri", ("thanks_goodbye",)), ("natotela sana", ("thanks_goodbye",)), ("bwanji", ("greeting","how_are_you")),
 # situations, not product names
 ("i am a market trader and need money for stock", ("micro_loan","msme_loan","loans_overview",DYM)),
 ("i want to buy a motorbike for deliveries", ("trader_mobility_loan",)),
 ("my business needs money to expand", ("sme_loan","msme_loan","loans_overview",DYM)),
 ("i want to save for my child's school", ("kids_savings_account","savings_plan_account","savings_options",DYM)),
 ("i want to open an account for my son", ("kids_savings_account",)), ("i have money i want to keep for a year", ("term_deposit_account",DYM)),
 ("where can i put my money to earn interest", ("term_deposit_account","savings_options","invest_overview","savings_account",DYM)),
 ("i run a small shop", ("micro_loan","business_account",DYM)), ("i work for the government and need a loan", ("personal_loan",)),
 ("we are a church and want an account", ("business_account",)), ("i have a company", ("business_account",DYM)),
 ("i want to manage my money on my phone", ("digital_banking","online_banking","etumba_what_is",DYM)),
 ("can i check my balance online", ("online_banking","etumba_balance_check",DYM)),
 # question forms of products
 ("what is a term deposit", ("term_deposit_account",)), ("what interest do you give on savings", ("savings_account","savings_options",DYM)),
 ("what is tamanga plus", ("tamanga_plus_account",)), ("what's the difference between savings and savings plan", ("savings_plan_account","savings_options","savings_account",DYM)),
 ("is there a minimum balance", ("savings_account","current_account",DYM)), ("how long does a loan take", ("loan_apply_how","msme_loan",DYM)),
 ("do i need collateral", ("collateral_definition","loan_requirements")), ("can i get a loan without collateral", ("personal_loan","collateral_definition","loan_requirements",DYM)),
 ("what is the maximum loan amount", ("personal_loan","msme_loan","loans_overview",DYM)), ("can i open an account with my nrc only", ("account_opening_requirements",DYM)),
 ("do you have atms", ("etumba_cash_in_out",DYM,"branch_locator")), ("can i send money to mtn", ("etumba_transfer_mobile_money",)),
 ("how do i pay zesco with etumba", ("zesco_token","etumba_what_is","etumba_ussd",DYM)),
 ("are you open on sunday", ("opening_hours",)), ("what time does the ndola branch close", ("opening_hours","branch_locator")),
 # run-ons
 ("hello good morning i would like to know how i can open a savings account and what i need", ("account_opening_requirements","savings_account","account_opening_how","action:multi")),
 ("hi i want to apply for a business loan for my shop how do i do it", ("loan_apply_how","msme_loan","micro_loan",DYM)),
 ("good afternoon please can someone call me i want to open an account", ("human_handoff", LEAD, "account_opening_how")),
 # emoji / punctuation
 ("👍", ("acknowledgement","action:fallback","thanks_goodbye")), ("🙏", ("thanks_goodbye","action:fallback","acknowledgement")),
 ("???", ("action:fallback","action:clarify",DYM)), ("...", ("action:fallback","action:menu")), ("1", ("account_types_overview","action:fallback",DYM)),
 # urgent variants
 ("my atm card is missing", FRAUD), ("someone is using my account", FRAUD), ("i got a call from someone saying they are from ab bank asking for my pin", FRAUD),
 ("my etumba was hacked", FRAUD), ("money disappeared from my account", FRAUD), ("unauthorized transaction on my account", FRAUD),
 ("i want to report a staff member", ("flow:complaint","action:urgent")), ("very bad service at cairo branch", ("flow:complaint","action:urgent")),
 # out of scope
 ("what is the price of maize", OOS), ("can you give me a job", OOS), ("i want to apply for a job at ab bank", OOS),
 ("what is the dollar rate", OOS), ("how do i get a tpin", OOS), ("is it going to rain", OOS), ("do you sell insurance", OOS),
 ("i love you", ("compliment",) + OOS), ("who is the president of zambia", OOS),
]

# --- round 3: robustness and everyday banking
DYM = "action:did_you_mean"; LEAD = "flow:lead"; FRAUD = ("flow:fraud", "action:urgent")
OOS = ("out_of_scope", "action:fallback", DYM)
ANY = lambda b: True
SINGLES3 = [
 ("my account number is 1234567890 i want a loan", (lambda b: "loan" in b.text.lower(),)),
 ("I don't want a loan, I want to save money", ("savings_account","savings_options","savings_plan_account",DYM)),
 ("not a loan, an account", ("account_types_overview",DYM,"account_opening_how")),
 ("my card was stolen where is the nearest branch", FRAUD),
 ("is there a branch near manda hill", ("branch_locator",)), ("lsk branch", ("branch_locator",)),
 ("branches on the copperbelt", ("branch_locator",DYM)), ("kitwe or ndola branch", ("branch_locator",)),
 ("nearest atm", ("etumba_cash_in_out",DYM,"branch_locator","agent_locator")), ("how do i reset my etumba pin", ("credential_trouble",)),
 ("my card is blocked", (*FRAUD, "credential_trouble", DYM, "out_of_scope")), ("is my money safe with you", ("about_ab_bank",DYM)),
 ("are you open now", ("opening_hours",)), ("can i open an account today", ("account_opening_how","account_opening_requirements")),
 ("i want to deposit money", ("etumba_cash_in_out",DYM,"branch_locator","out_of_scope")),
 ("how do i transfer money to another bank", ("online_banking",DYM,"out_of_scope")),
 ("how do i get a debit card", (*OOS, "current_account", "tamanga_plus_account", "action:urgent_confirm")),
 ("do you have visa cards", (*OOS, "current_account")), ("can i get a cheque book", ("tamanga_plus_account","business_account",DYM,*OOS)),
 ("how do i close my account", (*OOS, "human_handoff")), ("i want to change my phone number on my account", (*OOS, "human_handoff")),
 ("what is the minimum balance for tamanga", ("current_account","fees_tamanga")), ("does savings account have charges", ("savings_account","fees_charges")),
 ("how many withdrawals can i make", ("savings_account",DYM)), ("can i withdraw from savings plan", ("savings_plan_account",)),
 ("what is the interest on term deposit", ("term_deposit_account",)), ("minimum amount for term deposit", ("term_deposit_account",)),
 ("can i open a usd account", ("current_account","business_account",DYM)), ("do you have dollar accounts", ("current_account",DYM)),
 ("how long does it take to open an account", ("account_opening_how",)),
 ("can someone come to my office to open an account", ("account_opening_how", "human_handoff", DYM)),
 ("loan for school fees", (*OOS, "personal_loan")), ("mortgage", (*OOS,)), ("car loan", ("trader_mobility_loan", *OOS)),
 ("i want to apply for a loan of K50000", ("loan_apply_how","loans_overview","msme_loan")),
 ("what are the loan requirements for a micro loan", ("loan_requirements","micro_loan")),
 ("hello my name is Mary and i want to open a savings account", ("savings_account","account_opening_how","savings_options")),
 ("good evening i lost my etumba phone", (*FRAUD, "etumba_what_is", DYM)),
 ("i was charged twice", ("flow:complaint","action:urgent",DYM,"fees_charges")),
 ("my etumba transaction failed", ("technical_issue","etumba_reversal","action:urgent_confirm:complaint",DYM)),
 ("money not received", ("etumba_reversal","action:urgent",DYM)),
 ("how do i buy airtime with etumba", ("etumba_ussd","etumba_what_is")), ("can i pay water bills", ("etumba_what_is","etumba_ussd",DYM)),
 ("what is ab bank", ("about_ab_bank",)), ("who owns ab bank", ("about_ab_bank",)), ("where is your head office", ("branch_locator","contact_details")),
 ("do you have an app", ("etumba_register","online_banking","digital_banking",DYM)), ("ussd code", ("etumba_ussd",)),
 ("i need a statement for visa application", ("bank_statement_request",)), ("reference letter", (*OOS, "bank_statement_request")),
]

# --- round 1: conversations
LEAD = "flow:lead"
def data(**kv):
    return lambda b: all(b.session.flow_state.get("data", {}).get(k) == v for k, v in kv.items())
def text(s): return "text:" + s
def no_flow(b): return b.session.active_flow is None
CONVOS = [
 ("product yes -> lead", [("tap","savings_plan_account"), ("say","yes", (LEAD, lambda b: "Savings Plan" in b.text))]),
 ("product yes please -> lead", [("tap","micro_loan"), ("say","yes please", LEAD)]),
 ("product sure -> lead", [("tap","term_deposit_account"), ("say","sure", LEAD)]),
 ("product 'i'm interested'", [("tap","sme_loan"), ("say","i'm interested", LEAD)]),
 ("product 'contact me'", [("tap","sme_loan"), ("say","contact me", LEAD)]),
 ("product no -> parent", [("tap","savings_plan_account"), ("say","no", "savings_options")]),
 ("product no thanks -> parent", [("tap","micro_loan"), ("say","no thanks", ("business_loan_options","thanks_goodbye"))]),
 ("product maybe later", [("tap","micro_loan"), ("say","maybe later", (text("no problem"), "thanks_goodbye", "business_loan_options"))]),
 ("product not now", [("tap","micro_loan"), ("say","not now", (text("no problem"), "thanks_goodbye", "business_loan_options"))]),
 ("tell me more", [("tap","savings_account"), ("say","tell me more", "action:details")]),
 ("more details typed", [("tap","savings_account"), ("say","more details", "action:details")]),
 ("more info", [("tap","current_account"), ("say","more info", "action:details")]),
 ("typed back", [("tap","micro_loan"), ("say","back", "business_loan_options")]),
 ("go back", [("tap","micro_loan"), ("say","go back", "business_loan_options")]),
 ("tamanga how much", [("say","tell me about tamanga"), ("say","how much is it?", ("fees_tamanga","current_account"))]),
 ("tamanga monthly fee", [("tap","current_account"), ("say","what is the monthly fee", ("fees_tamanga",))]),
 ("savings what do i need", [("tap","savings_account"), ("say","what do i need to open it", "account_opening_requirements")]),
 ("etumba how register", [("say","what is etumba"), ("say","how do i register", "etumba_register")]),
 ("kitwe then hours", [("say","where is the kitwe branch"), ("say","what time does it open", "opening_hours")]),
 ("hours then saturday", [("say","what are your opening hours"), ("say","and on saturday?", "opening_hours")]),
 ("menu numbers", [("say","hi"), ("say","2", "loans_overview"), ("say","1", "business_loan_options"), ("say","2", "micro_loan"), ("say","yes", LEAD)]),
 ("menu 1 accounts", [("say","hello"), ("say","1", "account_types_overview")]),
 ("menu typed label", [("say","hi"), ("say","digital banking", "digital_banking"), ("say","online banking", "online_banking")]),
 ("loans then motorbike", [("say","loans"), ("say","for a motorbike", "trader_mobility_loan")]),
 ("lead my name is", [("tap","human_handoff"), ("say","my name is Mary Banda", data(name="Mary Banda"))]),
 ("lead i am", [("tap","human_handoff"), ("say","I am John Phiri", data(name="John Phiri"))]),
 ("lead its", [("tap","human_handoff"), ("say","it's Chanda", data(name="Chanda"))]),
 ("lead lowercase name", [("tap","human_handoff"), ("say","mary banda", lambda b: b.session.flow_state["data"].get("name","").lower()=="mary banda")]),
 ("lead hello at name", [("tap","human_handoff"), ("say","hello", lambda b: "name" not in b.session.flow_state.get("data",{}))]),
 ("lead thanks at name", [("tap","human_handoff"), ("say","ok", lambda b: "name" not in b.session.flow_state.get("data",{}))]),
 ("lead why name", [("tap","human_handoff"), ("say","why do you need my name?", lambda b: "name" not in b.session.flow_state.get("data",{}))]),
 ("lead phone intl", [("tap","human_handoff"), ("say","Mary"), ("say","+260 977 123 456", data(phone="0977123456"))]),
 ("lead phone in sentence", [("tap","human_handoff"), ("say","Mary"), ("say","you can call me on 0977123456", data(phone="0977123456"))]),
 ("lead phone refuse", [("tap","human_handoff"), ("say","Mary"), ("say","i don't want to give my number", lambda b: b.session.active_flow == "lead")]),
 ("lead time any time", [("tap","human_handoff"), ("say","Mary"), ("say","0977123456"), ("say","any time", data(time="Anytime"))]),
 ("lead time morning typed", [("tap","human_handoff"), ("say","Mary"), ("say","0977123456"), ("say","in the morning", data(time="Morning"))]),
 ("lead time evening", [("tap","human_handoff"), ("say","Mary"), ("say","0977123456"), ("say","evening", lambda b: b.session.flow_state["data"].get("time"))]),
 ("lead consent yes please", [("tap","human_handoff"), ("say","Mary"), ("say","0977123456"), ("say","morning"), ("say","yes please", data(marketing_consent="yes"))]),
 ("lead full + thanks", [("tap","lead:micro_loan"), ("say","Mary Banda"), ("say","0977123456"), ("say","anytime"), ("say","no"), ("say","yes", text("CBK-")), ("say","no thanks", "thanks_goodbye")]),
 ("lead summary change", [("tap","human_handoff"), ("say","Mary"), ("say","0977123456"), ("say","morning"), ("say","no"), ("say","change my number", lambda b: "phone" in b.text.lower() or "number" in b.text.lower())]),
 ("lead cancel", [("tap","human_handoff"), ("say","Mary"), ("say","cancel", (no_flow,))]),
 ("lead switch to question", [("tap","human_handoff"), ("say","Mary"), ("say","what are your opening hours?", "action:digression")]),
 ("two questions", [("say","what is etumba and how do i register for it", lambda b: b.last[1].get("intents") is not None or "register" in b.text.lower())]),
 ("welcome 8", [("say","hi"), ("say","8", ("action:fallback","action:did_you_mean","action:clarify",lambda b: True))]),
 ("after answer thanks", [("tap","opening_hours"), ("say","thanks", "thanks_goodbye")]),
 ("after thanks no", [("tap","opening_hours"), ("say","thanks"), ("say","no", "thanks_goodbye")]),
 ("after thanks yes", [("tap","opening_hours"), ("say","thanks"), ("say","yes", "action:menu")]),
 ("greet mid-convo", [("tap","opening_hours"), ("say","hi", "greeting")]),
 ("kids from savings menu", [("tap","savings_options"), ("say","kids", "kids_savings_account")]),
 ("savings menu number", [("tap","savings_options"), ("say","3", "kids_savings_account")]),
 ("invest yes", [("tap","invest_overview"), ("say","term deposit", "term_deposit_account"), ("say","yes", LEAD)]),
 ("complaint via feedback", [("tap","complaints_feedback"), ("say","submit a complaint", "flow:complaint")]),
 ("question after product", [("tap","savings_account"), ("say","where is the ndola branch", "branch_locator")]),
 ("open which account", [("tap","account_opening_how"), ("say","savings", LEAD)]),
 ("open which account 3", [("tap","account_opening_how"), ("say","3", LEAD)]),
]

# --- round 2: fresh journeys
LEAD = "flow:lead"
def data(**kv): return lambda b: all(b.session.flow_state.get("data", {}).get(k) == v for k, v in kv.items())
def text(s): return "text:" + s
def no_flow(b): return b.session.active_flow is None
def ticket(b): return "CBK-" in b.text or "CMP-" in b.text or "FRD-" in b.text
CONVOS2 = [
 ("full savings journey", [("say","hi"), ("say","I want to open an account", ("account_types_overview","account_opening_how")),
   ("say","savings", ("savings_options","savings_account",LEAD)), ("say","savings account", ("savings_account",LEAD)), ("say","yes", LEAD),
   ("say","Mwila Tembo", data(name="Mwila Tembo")), ("say","0966 111 222", data(phone="0966111222")), ("say","afternoon", data(time="Afternoon")),
   ("say","no", text("shall i send it")), ("say","yes", ticket), ("say","bye", "thanks_goodbye")]),
 ("loan journey", [("say","i need money for my shop", ("micro_loan","msme_loan","loans_overview","action:did_you_mean")),
   ("say","micro loan", "micro_loan"), ("say","ok call me", LEAD), ("say","Bupe", lambda b: "Micro Loan" in str(b.session.flow_state))]),
 ("etumba journey", [("say","etumba", "etumba_what_is"), ("say","how do i register", "etumba_register"), ("say","where can i find an agent", "agent_locator"), ("say","ok thanks", "thanks_goodbye")]),
 ("fraud preempts lead", [("tap","human_handoff"), ("say","Mary"), ("say","someone stole my card", ("flow:fraud","action:urgent"))]),
 ("bad then good phone", [("tap","human_handoff"), ("say","Mary"), ("say","0977", text("doesn't look like")), ("say","0977123456", data(phone="0977123456"))]),
 ("why number", [("tap","human_handoff"), ("say","Mary"), ("say","why do you need my number?", (text("call you"), text("so our team")))]),
 ("term deposit interest", [("tap","term_deposit_account"), ("say","what's the interest rate?", ("term_deposit_account","action:details",text("16%")))]),
 ("kids how old", [("tap","kids_savings_account"), ("say","how old must the child be?", (text("16"), "kids_savings_account","action:details"))]),
 ("yes after welcome", [("say","hi"), ("say","yes", ("acknowledgement","action:menu","bot_capabilities",text("how can i help"),text("what can i help")))]),
 ("nothing needed", [("say","hi"), ("say","i don't need anything", ("thanks_goodbye",))]),
 ("ask etumba after lead", [("tap","lead:micro_loan"), ("say","Mary"), ("say","0977123456"), ("say","morning"), ("say","no"), ("say","yes"),
   ("say","can you also tell me about etumba", "etumba_what_is")]),
 ("what after answer", [("tap","savings_account"), ("say","what?", "action:clarify")]),
 ("huh", [("tap","savings_account"), ("say","huh", "action:clarify")]),
 ("complaint journey", [("say","I want to complain", ("flow:complaint","action:urgent")), ("say","Service at a branch"),
   ("say","I waited three hours at cairo branch and nobody helped"), ("say","0977123456"), ("say","yes", ticket)]),
 ("gibberish x2", [("say","qwerty zxcv"), ("say","plmokn ijb", ("action:two_strike","action:fallback",text("person")))]),
 ("thanks then menu", [("tap","opening_hours"), ("say","thank you"), ("say","yes please", ("action:menu",))]),
 ("compare accounts", [("tap","current_account"), ("say","and tamanga plus?", "tamanga_plus_account")]),
 ("savings then plan", [("tap","savings_account"), ("say","what about the savings plan", "savings_plan_account")]),
 ("price question", [("tap","tamanga_plus_account"), ("say","how much does it cost", ("fees_charges","fees_tamanga",text("135")))]),
 ("branch then directions", [("say","where is the chipata branch"), ("say","what is their phone number", (text("phone"),"contact_details","branch_locator"))]),
 ("agent then branch", [("tap","agent_locator"), ("say","and the nearest branch in lusaka?", "branch_locator")]),
 ("restart mid menu", [("tap","loans_overview"), ("say","start over", "action:restart")]),
 ("name with title", [("tap","human_handoff"), ("say","Mr Banda", data(name="Mr Banda"))]),
 ("name only first", [("tap","human_handoff"), ("say","Chanda", data(name="Chanda"))]),
 ("name with hyphen", [("tap","human_handoff"), ("say","Mary-Jane Phiri", data(name="Mary-Jane Phiri"))]),
 ("time 'tomorrow morning'", [("tap","human_handoff"), ("say","Mary"), ("say","0977123456"), ("say","tomorrow morning", data(time="Morning"))]),
 ("time 'after 2pm'", [("tap","human_handoff"), ("say","Mary"), ("say","0977123456"), ("say","after 2pm", data(time="Afternoon"))]),
 ("consent 'ok'", [("tap","human_handoff"), ("say","Mary"), ("say","0977123456"), ("say","morning"), ("say","ok", data(marketing_consent="yes"))]),
 ("summary 'wrong name'", [("tap","human_handoff"), ("say","Mary"), ("say","0977123456"), ("say","morning"), ("say","no"), ("say","the name is wrong", text("full name"))]),
 ("interest after back", [("tap","micro_loan"), ("say","back"), ("say","sme loan", "sme_loan"), ("say","yes", (LEAD, lambda b: "SME Loan" in b.text))]),
 ("digital then online yes", [("tap","digital_banking"), ("say","online banking", "online_banking"), ("say","yes", LEAD)]),
 ("feedback compliment", [("tap","complaints_feedback"), ("say","i just want to say your staff were great", ("compliment","thanks_goodbye",text("thank")))]),
]


ALL_SINGLES = SINGLES + SINGLES2 + SINGLES3
ALL_CONVOS = CONVOS + CONVOS2


@pytest.mark.parametrize("text, expect", ALL_SINGLES, ids=[t for t, _ in ALL_SINGLES])
def test_single_message(bot, text, expect):
    b = bot()
    b.say(text)
    assert _ok(expect, b), (b.last[1], b.text[:200])


@pytest.mark.parametrize("name, turns", ALL_CONVOS, ids=[n for n, _ in ALL_CONVOS])
def test_conversation(bot, name, turns):
    b = bot()
    for i, turn in enumerate(turns):
        kind, value, expect = turn if len(turn) == 3 else (*turn, None)
        (b.tap if kind == "tap" else b.say)(value)
        if expect is not None:
            assert _ok(expect, b), (i, value, b.last[1], b.session.active_flow, b.text[:200])
