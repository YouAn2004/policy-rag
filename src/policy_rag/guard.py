"""Input guard. Catches messages that try to instruct the assistant instead of asking about a policy.

It is a list of plain patterns, so it is fast, gives the same result every time and runs before any search or model call.
It is not the access control. Restricted clauses are removed before retrieval whatever the message says.
"""

import re
import unicodedata

MESSAGE = ("That looks like an instruction to the assistant, not a question about a policy. "
           "Please ask about something in the handbook, such as leave, expenses, travel or IT security.")

# Patterns run on text lowercased, with punctuation turned into single spaces.
PATTERNS = [
    ("override", r"\b(ignore|disregard|forget|override|drop|skip)\b( all| any| your| the| my| these| those| every)*( previous| prior| above| earlier| original| other)*"
                 r" (instructions?|rules?|guidelines?|prompts?|restrictions?|programming|safeguards?|limits|constraints)"),
    ("override", r"\b(ignore|disregard|do not use|don t use|do not follow|don t follow|stop using) (the )?(handbook|policy|policies|clauses|context|documents)\b"),
    ("override", r"\bsystem override\b|\bnew instructions?\b|\bbegin (new )?(system )?(prompt|instructions?)\b|\bend of (context|clauses|policies|documents)\b"),
    ("mode", r"\b(admin|administrator|developer|debug|god|sudo|root|maintenance|unrestricted|jailbreak(en)?|dan) mode\b|\bjailbreak\b|\bno limits\b"),
    ("role play", r"\b(pretend|imagine|act|behave|roleplay|role play)\b.{0,25}\b(you are|you re|to be|as|like)\b.{0,30}\b(admin|administrator|hr director|director|ceo|executive|unrestricted|unfiltered|dan|developer|different ai|no rules|no limits)\b"),
    ("role play", r"\b(let s|lets) (role ?play|pretend)\b|\byou are now\b.{0,40}\b(admin|ai|assistant|bot|dan|free|unrestricted|developer)\b|\bfrom now on\b.{0,30}\byou\b"),
    ("bypass", r"\b(bypass|disable|turn off|remove|circumvent|get around|skip) (the |all |any |your )?(access|role|permission|security|safety|content)?( ?(filter|filters|check|checks|control|controls|restrictions?|rules?|limits?|protections?))\b"),
    ("role grab", r"\b(treat|consider|regard) me as (an? |the )?(admin|administrator|hr|executive|manager|finance|owner|root)\b"),
    ("role grab", r"\b(grant|give|allow|unlock) me\b.{0,15}\b(full |admin |hr |executive |root |unrestricted )?(access|permissions?|privileges?|rights)\b"),
    ("role grab", r"\b(switch|change|set|upgrade|elevate) (my )?(role|access|permissions?|privileges?)( level)? to\b|\bi am (the )?(system )?(admin|administrator|developer|root)\b"),
    ("authority claim", r"\bi am (the |a |an |your )?(ceo|cfo|coo|cto|owner|boss|director|admin|administrator|auditor|regulator)\b.{0,60}\b(allowed|authori[sz]ed|permitted|entitled|cleared|have the right)\b"),
    ("dump", r"\b(print|show|list|dump|output|reveal|display|leak|export|send|give|tell|read out|repeat)\b.{0,25}\b(every|all|each|entire|full|whole|complete)\b.{0,25}"
             r"\b(polic(y|ies)|clauses?|documents?|handbook|text|contents?)\b.{0,50}\b(you (can see|have|know|hold|were given|are holding)|in your (context|memory|database|knowledge)|including|that i (can t|cannot|am not allowed))"),
    ("dump", r"\b(print|show|list|dump|output|reveal|display|leak|export|send|give|tell|read out|repeat)\b.{0,30}\b(restricted|hidden|confidential|secret|classified|forbidden|private)\b.{0,15}"
             r"\b(polic(y|ies)|clauses?|documents?|ones|text|contents?|files?)\b"),
    ("dump", r"\bincluding (the )?(restricted|hidden|confidential|secret|forbidden)\b|\b(my|your) role (can t|cannot|isn t allowed to|is not allowed to) (read|see|access)\b"),
    ("dump", r"\b(full|entire|whole|raw|complete) (contents?|text|dump) of (your|the) (context|prompt|memory|clauses|documents|database)\b"),
    ("prompt leak", r"\b(reveal|show|print|repeat|output|tell me|display|give me|what (is|are|was|were)) (me )?(your|the) (system |hidden |secret |initial |original |full )*(prompt|instructions?|guidelines|rules)\b"),
    ("prompt leak", r"\brepeat (everything|the text|the words) (above|before)\b|\bword for word\b.{0,30}\b(prompt|instructions)\b|\bwhat were you (told|instructed)\b"),
    ("output control", r"\b(do not|don t|never|without) (cite|citing|citations|mention(ing)? the (policy|clause))\b"),
    ("output control", r"\b(just|simply|only) (say|answer|reply|respond|write)\b.{0,15}\b(yes|no|that the policy|that it is allowed|allowed)\b|\bsay that the (policy|handbook) (allows|permits|says)\b"),
]
COMPILED = [(name, re.compile(p)) for name, p in PATTERNS]
TAGS = re.compile(r"</?\s*(system|assistant|context|instructions?)\s*>|\[/?inst\]|<\|[a-z_]+\|>|#{2,}\s*(system|instruction)", re.I)


def normalise(text):
    text = unicodedata.normalize("NFKC", text).lower()
    text = "".join(ch for ch in text if unicodedata.category(ch) not in ("Cf", "Cc") or ch in "\n\t")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def check(question):
    """Name of the first pattern group that matches, or None for an ordinary question."""
    if TAGS.search(question):
        return "prompt markup"
    flat = normalise(question)
    for name, pattern in COMPILED:
        if pattern.search(flat):
            return name
    return None
