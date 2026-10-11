"""Persistent, loopback-only test inventory. Coins have no monetary value."""
from contextlib import contextmanager
import json, secrets, sqlite3, threading, time
from pathlib import Path
class Economy:
 def __init__(self,path,catalog):
  self.path=str(path);self.catalog=list(catalog);self.lock=threading.RLock()
  with self.db() as c:
   c.executescript('''CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY, token TEXT UNIQUE, name TEXT, coins INTEGER);
CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY, owner TEXT, skin TEXT);
CREATE TABLE IF NOT EXISTS offers(id TEXT PRIMARY KEY, sender TEXT, receiver TEXT, give TEXT, take TEXT, status TEXT, created REAL);
CREATE TABLE IF NOT EXISTS listings(id TEXT PRIMARY KEY, seller TEXT, item TEXT, price INTEGER, status TEXT, buyer TEXT);
CREATE TABLE IF NOT EXISTS receipts(owner TEXT, item TEXT, seen INTEGER DEFAULT 0);''')
 @contextmanager
 def db(self):
  from account_storage import connect
  c=connect(self.path,getattr(self,"remote_database",None))
  try:
   yield c
   c.commit()
  except BaseException:
   # A remote transaction can already be closed; never mask the original error.
   try:c.rollback()
   except Exception:pass
   raise
  finally:c.close()
 def request(self,m):
  with self.lock,self.db() as c:
   action=m.get('action','state');token=m.get('token','')
   if action!='state':c.execute('BEGIN IMMEDIATE')
   a=c.execute('SELECT * FROM accounts WHERE token=?',(token,)).fetchone()
   if action=='login' and not token:
    uid=secrets.token_hex(5);token=secrets.token_urlsafe(32);name=str(m.get('name','Player')).strip()[:24] or 'Player'
    c.execute('INSERT INTO accounts VALUES(?,?,?,?)',(uid,token,name,10000))
    c.executemany('INSERT INTO items VALUES(?,?,?)',[(secrets.token_hex(10),uid,s) for s in self.catalog])
    a=c.execute('SELECT * FROM accounts WHERE id=?',(uid,)).fetchone()
   if not a:raise ValueError('Profile unavailable. Sign in again.')
   uid=a['id'];result={}
   if action=='rename':
    name=str(m.get('name','')).strip()
    if not name or len(name)>24:raise ValueError('Name must contain 1–24 characters.')
    c.execute('UPDATE accounts SET name=? WHERE id=?',(name,uid))
   elif action=='offer':
    other=str(m.get('target',''));give=m.get('give',[]);take=m.get('take',[])
    if other==uid or not c.execute('SELECT id FROM accounts WHERE id=?',(other,)).fetchone():raise ValueError('Choose another local player.')
    if not isinstance(give,list) or not isinstance(take,list) or not give or not take or len(give)>10 or len(take)>10 or len(set(give+take))!=len(give+take):raise ValueError('Choose 1–10 different items on each side.')
    for owner,items in [(uid,give),(other,take)]:
     for item in items:self.available(c,item,owner)
    if c.execute("SELECT count(*) FROM offers WHERE sender=? AND status='pending'",(uid,)).fetchone()[0]>=20:raise ValueError('Too many pending offers.')
    oid=secrets.token_hex(10);c.execute('INSERT INTO offers VALUES(?,?,?,?,?,?,?)',(oid,uid,other,json.dumps(give),json.dumps(take),'pending',time.time()));result['message']='Trade offer sent.'
   elif action in ('accept','reject','cancel'):
    o=c.execute('SELECT * FROM offers WHERE id=?',(m.get('target'),)).fetchone()
    if not o or o['status']!='pending':raise ValueError('This trade is no longer pending.')
    if uid!=(o['sender'] if action=='cancel' else o['receiver']):raise ValueError('This offer belongs to another player.')
    status={'accept':'accepted','reject':'rejected','cancel':'cancelled'}[action]
    if action=='accept':
     give=json.loads(o['give']);take=json.loads(o['take'])
     for owner,items in [(o['sender'],give),(o['receiver'],take)]:
      for item in items:self.available(c,item,owner)
     for owner,items in [(o['receiver'],give),(o['sender'],take)]:
      for item in items:c.execute('UPDATE items SET owner=? WHERE id=?',(owner,item));c.execute('INSERT INTO receipts(owner,item) VALUES(?,?)',(owner,item))
     self.invalidate(c,give+take)
    c.execute('UPDATE offers SET status=? WHERE id=?',(status,o['id']));result['message']='Trade '+status+'.'
   elif action=='sell':
    item=m.get('target');price=m.get('price');self.available(c,item,uid)
    if type(price)!=int or not 1<=price<=1000000:raise ValueError('Price must be a whole number from 1 to 1000000.')
    c.execute('INSERT INTO listings VALUES(?,?,?,?,?,?)',(secrets.token_hex(10),uid,item,price,'active',''));self.invalidate(c,[item]);result['message']='Listed on the market.'
   elif action in ('buy','unlist'):
    listing=c.execute("SELECT * FROM listings WHERE id=? AND status='active'",(m.get('target'),)).fetchone()
    if not listing:raise ValueError('This listing is no longer available.')
    if action=='unlist':
     if listing['seller']!=uid:raise ValueError('This listing belongs to another player.')
     c.execute("UPDATE listings SET status='cancelled' WHERE id=?",(listing['id'],))
    else:
     if listing['seller']==uid:raise ValueError('You already own this item.')
     if a['coins']<listing['price']:raise ValueError('Not enough coins.')
     if not c.execute('SELECT id FROM items WHERE id=? AND owner=?',(listing['item'],listing['seller'])).fetchone():raise ValueError('Item unavailable.')
     c.execute('UPDATE accounts SET coins=coins-? WHERE id=?',(listing['price'],uid));c.execute('UPDATE accounts SET coins=coins+? WHERE id=?',(listing['price'],listing['seller']));c.execute('UPDATE items SET owner=? WHERE id=?',(uid,listing['item']));c.execute("UPDATE listings SET status='sold',buyer=? WHERE id=?",(uid,listing['id']));c.execute('INSERT INTO receipts(owner,item) VALUES(?,?)',(uid,listing['item']));self.invalidate(c,[listing['item']])
    result['message']='Purchase complete.' if action=='buy' else 'Listing removed.'
   elif action=='seen':c.execute('UPDATE receipts SET seen=1 WHERE owner=?',(uid,))
   elif action not in ('state','login','rename'):raise ValueError('Unknown action.')
   account=dict(c.execute('SELECT id,name,coins FROM accounts WHERE id=?',(uid,)).fetchone())
   users=[dict(row) for row in c.execute('SELECT id,name FROM accounts ORDER BY name')]
   items=[dict(row) for row in c.execute('SELECT * FROM items')]
   offers=[]
   for row in c.execute('SELECT * FROM offers WHERE sender=? OR receiver=? ORDER BY created DESC LIMIT 100',(uid,uid)):
    o=dict(row);o['give']=json.loads(o['give']);o['take']=json.loads(o['take']);offers.append(o)
   market=[dict(row) for row in c.execute("SELECT * FROM listings WHERE status='active' OR seller=? OR buyer=? ORDER BY rowid DESC LIMIT 500",(uid,uid))]
   received=[r[0] for r in c.execute('SELECT item FROM receipts WHERE owner=? AND seen=0',(uid,))]
   return dict(ok=True,token=token,account=account,users=users,items=items,offers=offers,market=market,received=received,**result)
 def available(self,c,item,owner):
  if not isinstance(item,str) or not c.execute('SELECT id FROM items WHERE id=? AND owner=?',(item,owner)).fetchone():raise ValueError('Item ownership changed. Refresh the offer.')
  if c.execute("SELECT id FROM listings WHERE item=? AND status='active'",(item,)).fetchone():raise ValueError('Remove this item from the market first.')
 def invalidate(self,c,items):
  for row in c.execute("SELECT id,give,take FROM offers WHERE status='pending'").fetchall():
   if set(items).intersection(json.loads(row['give'])+json.loads(row['take'])):c.execute("UPDATE offers SET status='expired' WHERE id=?",(row['id'],))
