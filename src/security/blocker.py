"""Regex gate for SQL, command, XSS, and obfuscated injection."""

from __future__ import annotations

import logging
import re
import urllib.parse

logger = logging.getLogger(__name__)

# A bare "select"/"drop" used as English ("select a shipping option", "dropdown")
# is not an injection. SQL still matches when the next token is not an article.
_ENGLISH_SELECT = r"(?!\s+(?:a|an|the|my|your|this|that|one|some|any|our)\b)"
_ENGLISH_DROP = r"(?!\s+(?:off|by|in|out|the|a|an|my|your)\b)"


class SecurityBlocker:
    """Match injection patterns on the raw query and its decoded form."""

    def __init__(self) -> None:
        self.dangerous_patterns = [
            r"DROP\s+DATABASE",
            r"DROP\s+SCHEMA\s+.*CASCADE",
            r"DROP\s+ALL\s+TABLES",
            r"DROP\s+TABLE\s+.*CASCADE",
            r"TRUNCATE\s+TABLE\s+.*CASCADE",
            r"ALTER\s+TABLE\s+.*DROP\s+COLUMN",
            r"DROP\s+INDEX",
            r"DROP\s+TRIGGER",
            r"DROP\s+FUNCTION",
            r"DROP\s+VIEW",
            r"DROP\s+SEQUENCE",
            r"DROP\s+USER",
            r"REVOKE\s+ALL\s+PRIVILEGES",
            r"ALTER\s+SYSTEM\s+SET",
            r"DROP\s+TABLESPACE",
            r"EXEC\s+sp_configure",
            r"EXEC\s+xp_cmdshell.*rm\s+-rf",
            r"EXEC\s+xp_cmdshell.*del",
            r"EXEC\s+sp_MSforeachtable",
            r"D/\*.*\*/ROP",
            r"DR/\*.*\*/OP",
            r"exec\s*\(\s*['\"]DROP",
            r"PREPARE\s+.*DROP",
            r"DROP\s+TABLE",
            r"'\s*OR\s*'1'\s*=\s*'1",
            r"'\s*OR\s*1\s*=\s*1",
            r"'=1\s*--",
            r"--",
            r"#",
            r"/\*",
            r"\*/",
            r"UNION\s+SELECT.*FROM",
            r"UNION\s+SELECT\s+NULL",
            r"UNION\s+ALL\s+SELECT",
            r"UNION\s+SELECT\s+@@version",
            r"UNION\s+SELECT.*information_schema",
            r"'\s*AND\s*1\s*=\s*1",
            r"'\s*AND\s*IF",
            r"'\s*AND\s*SLEEP",
            r"'\s*AND\s*\(SELECT",
            r"SUBSTRING\s*\(\s*SELECT",
            r"WAITFOR\s+DELAY",
            r"SLEEP\s*\(",
            r"pg_sleep",
            r"DBMS_PIPE\.RECEIVE_MESSAGE",
            r"BENCHMARK\s*\(",
            r"SELECT\s+LOAD_FILE",
            r"INTO\s+OUTFILE",
            r"xp_cmdshell",
            r"master\.\.sysdatabases",
            r"UTL_INADDR",
            r"UTL_HTTP",
            r"DBMS_PIPE",
            r";\s*DROP\s+TABLE",
            r";\s*DELETE\s+FROM",
            r";\s*UPDATE\s+.*SET",
            r";\s*INSERT\s+INTO",
            r";\s*CREATE\s+TABLE",
            r";\s*TRUNCATE\s+TABLE",
            r"GROUP_CONCAT",
            r"LOAD_FILE",
            r"GRANT\s+ALL\s+PRIVILEGES",
            r"super_priv",
            r"user_privileges",
            r'\{\s*"?\$ne"?\s*:',
            r'\{\s*"?\$gt"?\s*:',
            r'\{\s*"?\$where"?\s*:',
            r"\$ne\b",
            r"\$gt\b",
            r"\$where\b",
            r"SELECT\s+@@version",
            r"SELECT\s+@@hostname",
            r"SELECT\s+@@datadir",
            r"SELECT\s+USER\(\)",
            r"SELECT\s+CURRENT_USER\(\)",
            r"SELECT\s+SYSTEM_USER\(\)",
            r"<\s*script",
            r"javascript\s*:",
            r"on(?:load|click|mouseover|error|submit)\s*=",
            r"\brm\b",
            r"\bsudo\b",
            r"execute.*command",
            r"ignore.*instructions",
            r"harmful.*assistant",
            r"\*\*\*",
            r"rm\s+-[rf]+\s+",
            r";\s*rm\s+-[rf]+",
            r";\s*wget\s+",
            r";\s*curl\s+",
            r";\s*nc\s+",
            r";\s*ping\s+-",
            r"\.\./",
            r"\.\.\\",
            r"/etc/passwd",
            r"etcpasswd",
            r"c:\\windows\\system32",
            r"ping.*-[ls]\s*65\d*",
            r"fork.*bomb",
            r"A{64,}",
            r"%x{100,}",
            r"(?:%s){2,}",
            r"\$\{jndi:",
            r"\$\{env:",
            r"\$\{ctx:",
            r"slowloris",
            r"synflood",
            r"tcpkill",
            r"(?:sudo|rm|wget|curl|nc)\s+.*-[rflsp]+",
            r"&&\s*(?:rm|wget|curl)",
            r"\|\|\s*(?:rm|wget|curl)",
            r"`.*(?:rm|wget|curl).*`",
            r"\)\s*\(\s*\|",
            r"\{\{.*?\}\}",
            r"<\s*/?\s*h[1-6]\b",
            r"<\s*img\b",
            r"document\.cookie",
            r"\bbash\b",
            r"/dev/tcp",
            r"\bpowershell\b",
            r'"role"\s*:\s*"admin"',
            r"=\s*cmd\b",
            r"\bcalc\b",
            r"\(\.\*\)\+",
            r"__proto__",
            r"\biframe\b",
            r"\.php\b",
            r"\s{8,}",
            rf"\bselect\b{_ENGLISH_SELECT}",
            rf"\bdrop\b{_ENGLISH_DROP}",
            r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{40,}={0,2}(?![A-Za-z0-9+/])",
        ]
        self.obfuscation_patterns = [
            r"\b(?:s3l3ct|s3lect|sel3ct|5elect|se1ect|selec7|5el3ct|5e1ect|s31ect|s313ct)\b",
            r"\b(?:dr0p|d7op|dr9p)\b",
            r"\b(?:un10n|uni0n|un1on|un!on|un!0n|uni9n)\b",
            r"(?:1\s*=\s*1|l\s*=\s*l)",
            r"\b(?:adm1n|4dmin|@dmin|admin1|@dm1n)\b",
            r"\b(?:p@ssw0rd|p@55w0rd|passw0rd|pa55word)\b",
            r"\b(?:sleect|selct|selecct|slect|seelct)\b",
            r"\b(?:drp|dropp|dorp|dorpp|dop)\b",
            r"\b(?:unoin|iunon|unnion|unioon|ubion)\b",
            r"\b(?:whre|wheer|wherr|wherre)\b",
            r"\b(?:udpate|updaet|updte|updatte)\b",
            r"\b(?:isner|insret|insetr|insrt)\b",
            r"\b(?:delte|deleet|deleete|delet)\b",
            r"%(?:[0-9A-Fa-f]{2})+",
            r"(?:\\x[0-9A-Fa-f]{2})+",
            rf"\bS(?:\s|/\*.*?\*/)*E(?:\s|/\*.*?\*/)*L(?:\s|/\*.*?\*/)*E(?:\s|/\*.*?\*/)*C(?:\s|/\*.*?\*/)*T\b{_ENGLISH_SELECT}",
            r"\bU(?:\s|/\*.*?\*/)*N(?:\s|/\*.*?\*/)*I(?:\s|/\*.*?\*/)*O(?:\s|/\*.*?\*/)*N\b",
            rf"\bD(?:\s|/\*.*?\*/)*R(?:\s|/\*.*?\*/)*O(?:\s|/\*.*?\*/)*P\b{_ENGLISH_DROP}",
            rf"\bs.{{0,2}}e.{{0,2}}l.{{0,2}}e.{{0,2}}c.{{0,2}}t\b{_ENGLISH_SELECT}",
            rf"\bd.{{0,2}}r.{{0,2}}o.{{0,2}}p\b{_ENGLISH_DROP}",
            r"\bu.{0,2}n.{0,2}i.{0,2}o.{0,2}n\b",
            r"%25[0-9A-Fa-f]{2}",
            r"(?:ｓｅｌｅｃｔ|ｄｒｏｐ|ｕｎｉｏｎ)",
            r"(?:＜script＞)",
            r"(?:%73%65%6c%65%63%74|%64%72%6f%70)",
            r"(?:/*!50000select*/)",
            r"(?:concat\(.{1,30}\))",
            r"(?:char\([0-9,]+\))",
            r"\bu%6eion\b",
            r"\bd%72op\b",
            r"[A-Za-z0-9_%@$]{3,}[=<>!]{1,2}[A-Za-z0-9_%@$]+",
            r"%53%45%4c%45%43%54",
            r"%44%52%4f%50",
            r"%55%4e%49%4f%4e",
            r"%53%65%6c%65%63%74",
            r"%64%72%6f%70",
        ]
        self.patterns = [
            re.compile(pattern, re.IGNORECASE | re.MULTILINE)
            for pattern in self.dangerous_patterns + self.obfuscation_patterns
        ]

    def _preprocess_query(self, query: str) -> str:
        """URL-decode and fold leetspeak so encoded keywords become readable."""
        processed = query
        try:
            decoded = urllib.parse.unquote(processed)
            if decoded != processed:
                processed = decoded
                second = urllib.parse.unquote(processed)
                if second != processed:
                    processed = second
        except Exception:
            pass

        substitutions = {
            "0": "o",
            "1": "l",
            "3": "e",
            "4": "a",
            "5": "s",
            "6": "g",
            "7": "t",
            "8": "b",
            "9": "g",
            "@": "a",
            "$": "s",
            "+": "t",
            "!": "i",
        }
        folded = processed
        for char, replacement in substitutions.items():
            folded = folded.replace(char, replacement)
        return folded

    def evaluate_query(self, query: str) -> dict:
        """Return BLOCKED when the raw query or its normalized form matches."""
        processed = self._preprocess_query(query)
        matches: list[str] = []
        seen: set[str] = set()
        candidates = (query,) if processed == query else (query, processed)
        for candidate in candidates:
            for pattern in self.patterns:
                if pattern.pattern in seen:
                    continue
                if pattern.search(candidate):
                    seen.add(pattern.pattern)
                    matches.append(pattern.pattern)
        return {
            "status": "BLOCKED" if matches else "PASS",
            "matches": matches,
            "query": query,
        }


def evaluate_prompt(query: str) -> str:
    """Return ``BLOCKED`` or ``PASS`` for ``query``."""
    result = SecurityBlocker().evaluate_query(query)
    if result["matches"]:
        logger.warning("Malicious content detected in query: %s", query)
    return result["status"]
