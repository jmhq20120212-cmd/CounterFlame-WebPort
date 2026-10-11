"""Account-backed game inventory. Passwords and session tokens are stored as hashes."""
import hashlib, hmac, ipaddress, json, re, secrets, time
from economy import Economy
from community import Community, ACTIONS

class PlayerService(Community,Economy):
 def __init__(self,path,catalog,cases):
  from account_storage import remote_config
  self.remote_database=remote_config()
  catalog=catalog+json.loads((__import__('pathlib').Path(__file__).parent/'collectibles.json').read_text());super().__init__(path,[s['id'] for s in catalog]);self.skins={s['id']:s for s in catalog};self.cases={s['id']:s for s in cases}
  with self.db() as c:
   c.executescript('''CREATE TABLE IF NOT EXISTS credentials(owner TEXT PRIMARY KEY, username TEXT UNIQUE, salt TEXT, digest TEXT);
CREATE TABLE IF NOT EXISTS sessions(digest TEXT PRIMARY KEY, owner TEXT, expires REAL);
CREATE TABLE IF NOT EXISTS friends(sender TEXT, receiver TEXT, status TEXT, PRIMARY KEY(sender,receiver));
CREATE TABLE IF NOT EXISTS redemptions(owner TEXT, code TEXT, PRIMARY KEY(owner,code));
CREATE TABLE IF NOT EXISTS equipment(owner TEXT, weapon TEXT, skin TEXT, PRIMARY KEY(owner,weapon));
CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY, owner TEXT, skin TEXT, price INTEGER, status TEXT, item TEXT, seller TEXT);
CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, owner TEXT, action TEXT, detail TEXT, created REAL);
CREATE TABLE IF NOT EXISTS mission_progress(owner TEXT PRIMARY KEY, kills INTEGER DEFAULT 0, claimed INTEGER DEFAULT 0, xp INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS registration_rewards(network_key TEXT PRIMARY KEY, owner TEXT, created REAL);
CREATE TABLE IF NOT EXISTS auth_attempts(key TEXT PRIMARY KEY, count INTEGER, reset REAL);''')
  self.init_community()
 def record_kill(self,uid,weapon):
  if weapon!='p250':return
  with self.lock,self.db() as c:
   self._advance(c,uid,{'p250':1});c.execute('INSERT OR IGNORE INTO mission_progress(owner) VALUES(?)',(uid,));c.execute('UPDATE mission_progress SET kills=MIN(10,kills+1) WHERE owner=?',(uid,))
 @staticmethod
 def digest(token):return hashlib.sha256(token.encode()).hexdigest()
 def identity(self,token):
  if not isinstance(token,str) or not 20<=len(token)<=128:return None
  with self.db() as c:
   row=c.execute('SELECT a.id,a.name,a.token FROM sessions s JOIN accounts a ON a.id=s.owner WHERE s.digest=? AND s.expires>?',(self.digest(token),time.time())).fetchone()
   return dict(row) if row else None
 def owns_skin(self,uid,skin):
  with self.db() as c:return c.execute("SELECT 1 FROM items WHERE owner=? AND skin=?",(uid,skin)).fetchone() is not None
 def _session(self,c,uid):
  token=secrets.token_urlsafe(32);c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),));c.execute('INSERT INTO sessions VALUES(?,?,?)',(self.digest(token),uid,time.time()+30*86400));return token
 def authenticate(self,m,peer):
  username=str(m.get('username','')).strip().lower();password=m.get('password','');action=m['action']
  if not re.fullmatch(r'[a-z0-9_]{3,24}',username):raise ValueError('Username: 3–24 letters, numbers or underscores.')
  if not isinstance(password,str) or not 8<=len(password)<=128:raise ValueError('Password: 8–128 characters.')
  # Commit failed attempts too; rolling back this counter would defeat throttling.
  with self.lock,self.db() as c:
   key='auth:'+peer;row=c.execute('SELECT * FROM auth_attempts WHERE key=?',(key,)).fetchone();now=time.time()
   count=row['count'] if row and row['reset']>now else 0;reset=row['reset'] if row and row['reset']>now else now+60
   if count>=15:raise ValueError('Too many attempts. Wait one minute.')
   c.execute('INSERT OR REPLACE INTO auth_attempts VALUES(?,?,?)',(key,count+1,reset))
  with self.lock,self.db() as c:
   c.execute('BEGIN IMMEDIATE');cred=c.execute('SELECT * FROM credentials WHERE username=?',(username,)).fetchone()
   if action=='register':
    if cred:raise ValueError('Username unavailable.')
    uid=secrets.token_hex(5);salt=secrets.token_hex(16);digest=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600000).hex()
    address=ipaddress.ip_address(peer);address=getattr(address,'ipv4_mapped',None) or address
    network_key=self.digest('welcome:'+str(address))
    claimed=c.execute('SELECT 1 FROM registration_rewards WHERE network_key=?',(network_key,)).fetchone()
    bonus=0 if claimed else 1000
    if not claimed:c.execute('INSERT INTO registration_rewards VALUES(?,?,?)',(network_key,uid,time.time()))
    c.execute('INSERT INTO accounts VALUES(?,?,?,?)',(uid,secrets.token_urlsafe(32),username,bonus));c.execute('INSERT INTO credentials VALUES(?,?,?,?)',(uid,username,salt,digest));self.audit(c,uid,'register','Account created')
   else:
    salt=cred['salt'] if cred else '00'*16;digest=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600000).hex()
    if not cred or not hmac.compare_digest(digest,cred['digest']):raise ValueError('Incorrect username or password.')
    uid=cred['owner']
    address=ipaddress.ip_address(peer);address=getattr(address,'ipv4_mapped',None) or address
    c.execute('INSERT OR IGNORE INTO registration_rewards VALUES(?,?,?)',(self.digest('welcome:'+str(address)),uid,time.time()))
   return self._session(c,uid)
 @staticmethod
 def audit(c,uid,action,detail):c.execute('INSERT INTO history(owner,action,detail,created) VALUES(?,?,?,?)',(uid,action,str(detail)[:500],time.time()))
 def grant(self,c,uid,skin):
  item=secrets.token_hex(10);c.execute('INSERT INTO items VALUES(?,?,?)',(item,uid,skin));c.execute('INSERT INTO receipts(owner,item) VALUES(?,?)',(uid,item));return item
 def refill_test_coins(self,uid):
  username=__import__('os').environ.get('CF_UNLIMITED_COINS_USERNAME','').strip().lower()
  if not username:return
  with self.lock,self.db() as c:
   c.execute('UPDATE accounts SET coins=1000000000 WHERE id=? AND id IN (SELECT owner FROM credentials WHERE username=?)',(uid,username))
 def request(self,m,peer='127.0.0.1'):
  if not isinstance(m,dict):raise ValueError('Invalid request.')
  action=m.get('action','state');token=m.get('token','')
  if action in ('register','signin'):token=self.authenticate(m,peer)
  account=self.identity(token)
  if not account:raise ValueError('SIGN_IN_REQUIRED')
  self.refill_test_coins(account['id'])
  uid=account['id'];message='';reward='';view=str(m.get('profileId') or uid)
  if action=='signout':
   with self.db() as c:
    address=ipaddress.ip_address(peer);address=getattr(address,'ipv4_mapped',None) or address
    c.execute('INSERT OR IGNORE INTO registration_rewards VALUES(?,?,?)',(self.digest('welcome:'+str(address)),uid,time.time()))
    c.execute('DELETE FROM sessions WHERE digest=?',(self.digest(token),))
   return dict(ok=True,message='Signed out.')
  base_actions={'rename','offer','accept','reject','cancel','sell','buy','unlist','seen'}
  if action in ACTIONS:
   message,reward,view=self.community_request(m,uid)
  elif action in base_actions:
   result=super().request({**m,'token':account['token']})
   with self.db() as c:
    self.audit(c,uid,action,m.get('target') or m.get('name',''))
    if action=='buy':
     listing=c.execute('SELECT seller FROM listings WHERE id=?',(m.get('target'),)).fetchone()
     if listing:self.audit(c,listing['seller'],'sold',m.get('target'))
   message=result.get('message','').replace('local market','market').replace('local coins','coins').replace('local player','player')
  elif action not in ('state','register','signin'):
   with self.lock,self.db() as c:
    c.execute('BEGIN IMMEDIATE');target=str(m.get('target',''));price=m.get('price',0)
    if action=='equip':
     item=c.execute('SELECT * FROM items WHERE id=? AND owner=?',(target,uid)).fetchone()
     if not item or item['skin'] not in self.skins or self.skins[item['skin']]['weapon']=='graffiti':raise ValueError('You do not own this skin.')
     skin=self.skins[item['skin']];knives={'bayonet','butterfly','flipknife','gutknife','huntsman','karambit','knifect','knifetr','kukri','m9bayonet','nomad','paracod','shadowdaggers','skeleton','stiletto','talon'}
     if skin['weapon'] in knives:
      for knife in knives:c.execute('DELETE FROM equipment WHERE owner=? AND weapon=?',(uid,knife))
     c.execute('INSERT OR REPLACE INTO equipment VALUES(?,?,?)',(uid,skin['weapon'],skin['id']));message='Skin equipped.'
    elif action=='unequip':
     item=c.execute('SELECT skin FROM items WHERE id=? AND owner=?',(target,uid)).fetchone()
     if not item or item['skin'] not in self.skins:raise ValueError('You do not own this skin.')
     c.execute('DELETE FROM equipment WHERE owner=? AND weapon=? AND skin=?',(uid,self.skins[item['skin']]['weapon'],item['skin']));message='Skin unequipped.'
    elif action=='mission_claim':
     if target!='p250_10' or c.execute('UPDATE mission_progress SET claimed=1,xp=xp+2000 WHERE owner=? AND kills>=10 AND claimed=0',(uid,)).rowcount!=1:raise ValueError('Mission is incomplete or already claimed.')
     message='Mission claimed: +2000 XP.'
    elif action=='promo':
     code=target.strip().upper()
     rewards={'2026CASE':('case:grand_case','Grand Case'),'GIFTCASEPLS':('case:gift_case','Gift Box')}
     if code not in rewards:raise ValueError('Code not found.')
     if c.execute('SELECT 1 FROM redemptions WHERE owner=? AND code=?',(uid,code)).fetchone():raise ValueError('Code already redeemed.')
     c.execute('INSERT INTO redemptions VALUES(?,?)',(uid,code));skin,name=rewards[code];reward=self.grant(c,uid,skin);message='Received: '+name
    elif action=='case_buy':
     case=self.cases.get(target)
     if not case or target=='gift_case':raise ValueError('Case unavailable.')
     if c.execute('UPDATE accounts SET coins=coins-? WHERE id=? AND coins>=?',(case['price'],uid,case['price'])).rowcount!=1:raise ValueError('Not enough coins.')
     reward=self.grant(c,uid,'case:'+target);message='Case purchased.'
    elif action=='case_open':
     self.available(c,target,uid);item=c.execute('SELECT * FROM items WHERE id=?',(target,)).fetchone();case=self.cases.get(item['skin'].removeprefix('case:')) if item['skin'].startswith('case:') else None
     if not case:raise ValueError('Choose a case from your inventory.')
     pool=[s for s in case['contents'] if s in self.skins or s.startswith('case:') and s[5:] in self.cases]
     if not pool:raise ValueError('Case contents unavailable.')
     c.execute('DELETE FROM items WHERE id=?',(target,));self.invalidate(c,[target]);reward=self.grant(c,uid,secrets.choice(pool));message='Case opened.'
    elif action=='friend_add':
     if target==uid or not c.execute('SELECT id FROM accounts WHERE id=?',(target,)).fetchone():raise ValueError('Player ID not found.')
     if c.execute('SELECT 1 FROM friends WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?)',(uid,target,target,uid)).fetchone():raise ValueError('Friend or request already exists.')
     c.execute('INSERT INTO friends VALUES(?,?,?)',(uid,target,'pending'));message='Friend request sent.'
    elif action in ('friend_accept','friend_reject','friend_remove'):
     if action=='friend_remove':c.execute('DELETE FROM friends WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?)',(uid,target,target,uid))
     else:
      row=c.execute("SELECT * FROM friends WHERE sender=? AND receiver=? AND status='pending'",(target,uid)).fetchone()
      if not row:raise ValueError('Friend request unavailable.')
      if action=='friend_accept':c.execute("UPDATE friends SET status='accepted' WHERE sender=? AND receiver=?",(target,uid))
      else:c.execute('DELETE FROM friends WHERE sender=? AND receiver=?',(target,uid))
     message='Friends updated.'
    elif action=='request_buy':
     if target not in self.skins:raise ValueError('Skin unavailable.')
     if type(price)!=int or not 1<=price<=1000000:raise ValueError('Enter a whole-number price.')
     if c.execute("SELECT count(*) FROM requests WHERE owner=? AND status='active'",(uid,)).fetchone()[0]>=20:raise ValueError('Too many active requests.')
     if c.execute('UPDATE accounts SET coins=coins-? WHERE id=? AND coins>=?',(price,uid,price)).rowcount!=1:raise ValueError('Not enough coins.')
     c.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,?)',(secrets.token_hex(10),uid,target,price,'active','',''));message='Buy request created. Coins reserved.'
    elif action=='request_cancel':
     row=c.execute("SELECT * FROM requests WHERE id=? AND owner=? AND status='active'",(target,uid)).fetchone()
     if not row:raise ValueError('Request unavailable.')
     c.execute("UPDATE requests SET status='cancelled' WHERE id=?",(target,));c.execute('UPDATE accounts SET coins=coins+? WHERE id=?',(row['price'],uid));message='Request cancelled. Coins returned.'
    elif action=='request_fill':
     row=c.execute("SELECT * FROM requests WHERE id=? AND status='active'",(target,)).fetchone();item_id=m.get('item','')
     if not row or row['owner']==uid:raise ValueError('Request unavailable.')
     self.available(c,item_id,uid);item=c.execute('SELECT * FROM items WHERE id=?',(item_id,)).fetchone()
     if item['skin']!=row['skin']:raise ValueError('This skin does not match the request.')
     c.execute('UPDATE items SET owner=? WHERE id=?',(row['owner'],item_id));c.execute('UPDATE accounts SET coins=coins+? WHERE id=?',(row['price'],uid));c.execute("UPDATE requests SET status='filled',item=?,seller=? WHERE id=?",(item_id,uid,target));c.execute('INSERT INTO receipts(owner,item) VALUES(?,?)',(row['owner'],item_id));self.invalidate(c,[item_id]);self.audit(c,row['owner'],'request_filled',target);message='Request fulfilled.'
    else:raise ValueError('Unknown action.')
    self.audit(c,uid,action,target)
  self.refill_test_coins(uid)
  result=super().request(dict(action='state',token=account['token']))
  with self.db() as c:
   # Sold/traded skins cannot remain equipped after ownership changes.
   c.execute('DELETE FROM equipment WHERE owner=? AND NOT EXISTS(SELECT 1 FROM items WHERE owner=equipment.owner AND skin=equipment.skin)',(uid,))
   progress=c.execute('SELECT kills,claimed,xp FROM mission_progress WHERE owner=?',(uid,)).fetchone()
   result['missionKills']=min(10,progress['kills']) if progress else 0;result['missionClaimed']=bool(progress['claimed']) if progress else False;result['account']['xp']=progress['xp'] if progress else 0
   result['equipped']=[dict(r) for r in c.execute('SELECT weapon,skin FROM equipment WHERE owner=?',(uid,))]
   result['friends']=[dict(r) for r in c.execute('SELECT * FROM friends WHERE sender=? OR receiver=?',(uid,uid))]
   result['requests']=[dict(r) for r in c.execute("SELECT * FROM requests WHERE status='active' OR owner=? OR seller=? ORDER BY rowid DESC LIMIT 500",(uid,uid))]
   result['history']=[dict(r) for r in c.execute('SELECT action,detail,created FROM history WHERE owner=? ORDER BY id DESC LIMIT 100',(uid,))]
   result['received']=[r[0] for r in c.execute('SELECT r.item FROM receipts r JOIN items i ON i.id=r.item WHERE r.owner=? AND i.owner=? AND r.seen=0',(uid,uid))]
  with self.db() as c:result.update(self.community_state(c,uid,view))
  result['account']['xp']=result['progression']['xp']
  old=next(x for x in result['progression']['missions'] if x['id']=='p250_10');result['missionKills']=old['progress'];result['missionClaimed']=old['claimed']
  result.update(token=token,message=message,reward=reward);return result
