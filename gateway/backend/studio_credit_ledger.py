"""No-ad, no-contract internal *CPU edit* points. NOT external GPU credits.

Atomic SQLite reference implementation for a durable volume or on-device DB.
Render Free has EPHEMERAL storage; do not enable a monetary/entitlement wallet
there. No Google AdMob, reward SDK, payment collection, broker or ad network.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

OWNER = re.compile(r"^[0-9a-f]{64}$")
RECEIPT = re.compile(r"^[0-9a-f]{64}$")
MAX_BALANCE = 8
DAILY_GIFT = 3
DAILY_REUSE_BONUS = 2

class InvalidCredit(ValueError):pass
class InsufficientCredits(RuntimeError):pass

class EditPointLedger:
    def __init__(self,db:Path):
        self.db=Path(db)
        self.db.parent.mkdir(parents=True,exist_ok=True)
        with self._open() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS wallets(
                    owner TEXT PRIMARY KEY,
                    balance INTEGER NOT NULL DEFAULT 0
                    CHECK(balance>=0 AND balance<=8),
                    gift_day TEXT,
                    reuse_day TEXT,
                    reuse_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS journal(
                    owner TEXT NOT NULL, event_id TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    day TEXT NOT NULL,
                    PRIMARY KEY(owner,event_id)
                );
            """)

    def _open(self):
        conn=sqlite3.connect(str(self.db),timeout=10,isolation_level=None)
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    @staticmethod
    def _validate(owner,event):
        if not isinstance(owner,str) or not OWNER.fullmatch(owner):
            raise InvalidCredit("Owner identity must be hashed")
        if not isinstance(event,str) or len(event)>100 or not event.isascii():
            raise InvalidCredit("Invalid event ID")

    @staticmethod
    def _day(now):
        return (now or datetime.now(timezone.utc)).astimezone(
            timezone.utc).date().isoformat()

    def balance(self,owner:str)->int:
        self._validate(owner,"balance")
        with self._open() as c:
            row=c.execute("SELECT balance FROM wallets WHERE owner=?",(owner,)).fetchone()
            return row[0] if row else 0

    def gift(self,owner:str,*,now=None)->int:
        """Three CPU-edit points every UTC day, capped at wallet capacity."""
        self._validate(owner,"daily")
        day=self._day(now)
        with self._open() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("INSERT OR IGNORE INTO wallets(owner) VALUES (?)",(owner,))
            balance,last=c.execute(
                "SELECT balance,gift_day FROM wallets WHERE owner=?",(owner,)).fetchone()
            if last!=day:
                new=min(MAX_BALANCE,balance+DAILY_GIFT)
                amount=new-balance
                c.execute("UPDATE wallets SET balance=?,gift_day=? WHERE owner=?",
                          (new,day,owner))
                c.execute("INSERT OR IGNORE INTO journal VALUES (?,?,?,?,?)",
                          (owner,"daily:"+day,amount,"daily_gift",day))
            else:
                new=balance
            c.commit()
            return new

    def reward_reused_clip(self,owner:str,source_sha256:str,
                           *,verified_cache_hit:bool,now=None)->int:
        """One point for a real reuse that avoided a fresh CPU render.

        Calls to this method must come ONLY from a verified server-side cache
        result, never from an Android-provided boolean or media digest.
        """
        self._validate(owner,"reuse")
        if not isinstance(source_sha256,str) or not RECEIPT.fullmatch(source_sha256):
            raise InvalidCredit("No verifiable media hash")
        if not verified_cache_hit:
            raise InvalidCredit("Only server-verified saved work earns rewards")
        day=self._day(now)
        event="reuse:"+day+":"+source_sha256
        with self._open() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("INSERT OR IGNORE INTO wallets(owner) VALUES (?)",(owner,))
            balance,old_day,count=c.execute(
                "SELECT balance,reuse_day,reuse_count FROM wallets WHERE owner=?",
                (owner,)).fetchone()
            if old_day!=day:count=0
            if c.execute("SELECT 1 FROM journal WHERE owner=? AND event_id=?",
                         (owner,event)).fetchone():
                c.commit()
                return balance
            if count>=DAILY_REUSE_BONUS or balance>=MAX_BALANCE:
                c.commit()
                return balance
            c.execute("UPDATE wallets SET balance=balance+1,reuse_day=?,reuse_count=? WHERE owner=?",
                      (day,count+1,owner))
            c.execute("INSERT INTO journal VALUES (?,?,?,?,?)",
                      (owner,event,1,"verified_reuse",day))
            c.commit()
            return balance+1

    def spend_cpu_edit(self,owner:str,request_digest:str,*,now=None)->tuple[bool,int]:
        self._validate(owner,"edit")
        if not RECEIPT.fullmatch(request_digest):
            raise InvalidCredit("Invalid request hash")
        day=self._day(now)
        event="cpu:"+request_digest
        with self._open() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("INSERT OR IGNORE INTO wallets(owner) VALUES (?)",(owner,))
            balance=c.execute("SELECT balance FROM wallets WHERE owner=?",
                              (owner,)).fetchone()[0]
            if c.execute("SELECT 1 FROM journal WHERE owner=? AND event_id=?",
                         (owner,event)).fetchone():
                c.commit()
                return False,balance
            if balance<1:raise InsufficientCredits("No CPU-edit points remaining")
            c.execute("UPDATE wallets SET balance=balance-1 WHERE owner=?",(owner,))
            c.execute("INSERT INTO journal VALUES (?,?,?,?,?)",
                      (owner,event,-1,"cpu_edit",day))
            c.commit()
            return True,balance-1

    def refund_cpu_edit(self,owner:str,request_digest:str,*,now=None)->int:
        self._validate(owner,"refund")
        if not RECEIPT.fullmatch(request_digest):
            raise InvalidCredit("Invalid request hash")
        day=self._day(now)
        event="refund:"+request_digest
        with self._open() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("INSERT OR IGNORE INTO wallets(owner) VALUES (?)",(owner,))
            if c.execute("SELECT 1 FROM journal WHERE owner=? AND event_id=?",
                         (owner,event)).fetchone():
                return c.execute("SELECT balance FROM wallets WHERE owner=?",
                                 (owner,)).fetchone()[0]
            spent=c.execute("SELECT 1 FROM journal WHERE owner=? AND event_id=?",
                            (owner,"cpu:"+request_digest)).fetchone()
            if not spent:
                raise InvalidCredit("Cannot refund an edit that did not debit")
            balance=c.execute("SELECT balance FROM wallets WHERE owner=?",(owner,)).fetchone()[0]
            new=min(MAX_BALANCE,balance+1)
            c.execute("UPDATE wallets SET balance=? WHERE owner=?",(new,owner))
            c.execute("INSERT INTO journal VALUES (?,?,?,?,?)",
                      (owner,event,new-balance,"cpu_refund",day))
            c.commit()
            return new

def funding_contract()->dict:
    return {
       "ad_networks_enabled":False,"contracts_required":False,
       "in_app_cpu_edit_points_supported":True,
       "external_gpu_credit_redeemable":False,
       "money_value_usd":0,"transferable":False,
       "max_daily_free_gift":DAILY_GIFT,
       "max_daily_verified_reuse_reward":DAILY_REUSE_BONUS,
       "requires_durable_ledger_before_live_activation":True,
       "render_free_local_sqlite_durable":False,
    }
