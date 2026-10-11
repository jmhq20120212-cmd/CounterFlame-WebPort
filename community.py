"""Persistent profiles and server-earned progression; no client-submitted statistics."""
import base64, json, re, secrets, struct, time, zlib
from urllib.parse import urlparse

MISSIONS=(
 dict(id='p250_10',title='Get 10 kills with the P250',kind='p250',goal=10,xp=2000,period='career'),
 dict(id='daily_kills',title='Get 15 kills',kind='kills',goal=15,xp=1000,period='daily'),
 dict(id='daily_damage',title='Deal 1000 damage',kind='damage',goal=1000,xp=1000,period='daily'),
 dict(id='daily_match',title='Complete a match',kind='matches',goal=1,xp=750,period='daily'),
 dict(id='weekly_kills',title='Get 100 kills',kind='kills',goal=100,xp=4000,period='weekly'),
 dict(id='weekly_wins',title='Win 5 matches',kind='wins',goal=5,xp=3000,period='weekly'),
 dict(id='weekly_headshots',title='Get 25 headshot kills',kind='headshots',goal=25,xp=3000,period='weekly'))
SOCIALS={'telegram':{'t.me','telegram.me'},'youtube':{'youtube.com','www.youtube.com','youtu.be'},'twitch':{'twitch.tv','www.twitch.tv'},'tiktok':{'tiktok.com','www.tiktok.com'}}
ACTIONS={'profile','profile_save','profile_avatar','profile_vote','profile_comment','comment_delete','mission_claim','pass_claim','pass_buy','pass_levels','arsenal_buy','arsenal_stars'}

def period(m):
 day=int(time.time()//86400)
 return 'all' if m['period']=='career' else str(day if m['period']=='daily' else (day+3)//7)

class Community:
 def init_community(self):
  with self.db() as c:
   c.executescript('''CREATE TABLE IF NOT EXISTS profiles(owner TEXT PRIMARY KEY, description TEXT DEFAULT '', clan TEXT DEFAULT '', telegram TEXT DEFAULT '', youtube TEXT DEFAULT '', twitch TEXT DEFAULT '', tiktok TEXT DEFAULT '', avatar TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS profile_votes(owner TEXT, visitor TEXT, value INTEGER, PRIMARY KEY(owner,visitor));
CREATE TABLE IF NOT EXISTS profile_comments(id INTEGER PRIMARY KEY, owner TEXT, author TEXT, body TEXT, created REAL);
CREATE TABLE IF NOT EXISTS career(owner TEXT PRIMARY KEY, kills INTEGER DEFAULT 0, deaths INTEGER DEFAULT 0, damage INTEGER DEFAULT 0, matches INTEGER DEFAULT 0, wins INTEGER DEFAULT 0, headshots INTEGER DEFAULT 0, seconds INTEGER DEFAULT 0, rating INTEGER DEFAULT 1000, xp INTEGER DEFAULT 0, stars INTEGER DEFAULT 0, gold INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS quests(owner TEXT, quest TEXT, period TEXT, progress INTEGER DEFAULT 0, claimed INTEGER DEFAULT 0, PRIMARY KEY(owner,quest,period));
CREATE TABLE IF NOT EXISTS pass_claims(owner TEXT, reward TEXT, PRIMARY KEY(owner,reward));
CREATE TABLE IF NOT EXISTS match_history(owner TEXT, match TEXT, mode TEXT, map INTEGER, kills INTEGER, deaths INTEGER, damage INTEGER, result TEXT, rating INTEGER, seconds INTEGER, created REAL, PRIMARY KEY(owner,match));''')
   # Idempotent migration of previously earned P250 progress/XP.
   c.execute('INSERT OR IGNORE INTO career(owner,xp) SELECT owner,xp FROM mission_progress')
   c.execute("INSERT OR IGNORE INTO quests(owner,quest,period,progress,claimed) SELECT owner,'p250_10','all',kills,claimed FROM mission_progress")
  skins=list(self.skins.values());knives={'knifect','knifetr','karambit','butterfly','huntsman','m9bayonet','bayonet','falchion','flip','gut','bowie','shadowdaggers','navaja','stiletto','talon','ursus','classic','paracord','survival','nomad','skeleton'}
  self.arsenal=[]
  for key,name,stars,selection in [
   ('rifles','Rifle Collection',25,[s for s in skins if s['weapon'] in ('ak47','m4a1','m4a1s','famas','galil')]),
   ('pistols','Pistol Collection',15,[s for s in skins if s['weapon'] in ('usp','glock','p250','tec9','deserteagle')]),
   ('snipers','Sniper Collection',25,[s for s in skins if s['weapon'] in ('awp','ssg08')]),
   ('smgs','SMG Collection',15,[s for s in skins if s['weapon'] in ('ump45','mp9','mac10')]),
   ('gloves','Glove Collection',30,[s for s in skins if s['weapon']=='gloves']),
   ('knives','Knife Collection',30,[s for s in skins if s['weapon'] in knives])]:
   pool=[s['id'] for s in selection if not re.search(r'sex|porn',s['id']+' '+s.get('name',''),re.I)]
   if pool:self.arsenal.append(dict(id=key,name=name,price=stars,contents=pool))
 def _career(self,c,uid):c.execute('INSERT OR IGNORE INTO career(owner) VALUES(?)',(uid,))
 def _advance(self,c,uid,counts):
  self._career(c,uid)
  for m in MISSIONS:
   count=counts.get(m['kind'],0)
   if count<=0:continue
   p=period(m);c.execute('INSERT OR IGNORE INTO quests(owner,quest,period) VALUES(?,?,?)',(uid,m['id'],p));c.execute('UPDATE quests SET progress=MIN(?,progress+?) WHERE owner=? AND quest=? AND period=?',(m['goal'],count,uid,m['id'],p))
 def record_combat(self,attacker,victim,damage,killed,weapon,headshot=False):
  with self.lock,self.db() as c:
   c.execute('BEGIN IMMEDIATE')
   if attacker:
    self._advance(c,attacker,dict(damage=damage,kills=int(killed),p250=int(killed and weapon=='p250'),headshots=int(killed and headshot)))
    c.execute('UPDATE career SET damage=damage+?,kills=kills+?,headshots=headshots+?,xp=xp+? WHERE owner=?',(damage,int(killed),int(killed and headshot),25*int(killed),attacker))
   if killed:self._career(c,victim);c.execute('UPDATE career SET deaths=deaths+1 WHERE owner=?',(victim,))
 def record_match(self,uid,match,mode,map_id,kills,deaths,damage,result,seconds):
  with self.lock,self.db() as c:
   c.execute('BEGIN IMMEDIATE');self._career(c,uid);delta=20 if result=='WIN' else -10 if result=='LOSS' else 0
   if not c.execute('INSERT OR IGNORE INTO match_history VALUES(?,?,?,?,?,?,?,?,?,?,?)',(uid,match,mode,map_id,kills,deaths,damage,result,delta,seconds,time.time())).rowcount:return
   self._advance(c,uid,dict(matches=1,wins=int(result=='WIN')))
   c.execute('UPDATE career SET matches=matches+1,wins=wins+?,seconds=seconds+?,rating=MAX(0,rating+?),xp=xp+?,stars=stars+1 WHERE owner=?',(int(result=='WIN'),seconds,delta,300 if result=='WIN' else 150,uid))
 def profile(self,c,uid,viewer,read_only=False):
  account=c.execute('SELECT id,name FROM accounts WHERE id=?',(uid,)).fetchone()
  if not account:raise ValueError('Player not found.')
  c.execute('INSERT OR IGNORE INTO profiles(owner) VALUES(?)',(uid,));self._career(c,uid)
  # Finish idempotent initialization before the many read-only profile queries.
  # Mutation callers retain their encompassing transaction.
  if read_only:c.commit()
  p=dict(c.execute('SELECT * FROM profiles WHERE owner=?',(uid,)).fetchone());p.update(dict(account));p.update(dict(c.execute('SELECT * FROM career WHERE owner=?',(uid,)).fetchone()))
  p['level']=1+p['xp']//1000;p['kd']=round(p['kills']/max(1,p['deaths']),2);p['averageDamage']=round(p['damage']/max(1,p['matches']),1)
  p['rank']=1+c.execute('SELECT COUNT(*) FROM career WHERE rating>? OR (rating=? AND owner<?)',(p['rating'],p['rating'],uid)).fetchone()[0]
  p['likes']=c.execute('SELECT COUNT(*) FROM profile_votes WHERE owner=? AND value=1',(uid,)).fetchone()[0];p['dislikes']=c.execute('SELECT COUNT(*) FROM profile_votes WHERE owner=? AND value=-1',(uid,)).fetchone()[0]
  vote=c.execute('SELECT value FROM profile_votes WHERE owner=? AND visitor=?',(uid,viewer)).fetchone();p['vote']=vote[0] if vote else 0
  p['comments']=[dict(r) for r in c.execute('SELECT pc.*,a.name FROM profile_comments pc JOIN accounts a ON a.id=pc.author WHERE pc.owner=? ORDER BY pc.id DESC LIMIT 100',(uid,))]
  p['history']=[dict(r) for r in c.execute('SELECT * FROM match_history WHERE owner=? ORDER BY created DESC LIMIT 30',(uid,))]
  return p
 def community_request(self,m,uid):
  action=m['action'];target=str(m.get('target') or uid);message='';reward=''
  with self.lock,self.db() as c:
   c.execute('BEGIN IMMEDIATE');self._career(c,uid)
   if action=='profile':pass
   elif action=='profile_save':
    field=m.get('field');value=m.get('value','')
    if field not in ('description','clan',*SOCIALS) or not isinstance(value,str):raise ValueError('Invalid profile field.')
    value=value.strip()
    if len(value)>(500 if field=='description' else 8 if field=='clan' else 200) or any(ord(x)<32 and x not in '\n\t' for x in value):raise ValueError('Profile value is too long or invalid.')
    if field in SOCIALS and value:
     u=urlparse(value)
     if u.scheme!='https' or u.hostname not in SOCIALS[field] or u.username or u.password or u.port not in (None,443):raise ValueError('Enter an HTTPS link for '+field+'.')
    c.execute('INSERT OR IGNORE INTO profiles(owner) VALUES(?)',(uid,));c.execute('UPDATE profiles SET '+field+'=? WHERE owner=?',(value,uid));message='Profile saved.';target=uid
   elif action=='profile_avatar':
    value=m.get('value','')
    if not isinstance(value,str) or len(value)>220000:raise ValueError('Choose an image below 150 KB.')
    try:data=base64.b64decode(value,validate=True)
    except Exception:raise ValueError('Invalid image.')
    if not data.startswith(b'\x89PNG\r\n\x1a\n') or len(data)<33 or data[12:16]!=b'IHDR':raise ValueError('Choose a PNG image.')
    width,height=struct.unpack('>II',data[16:24])
    if not 1<=width<=256 or not 1<=height<=256:raise ValueError('Image must be at most 256 × 256.')
    # Validate the bounded PNG stream and CRC, rejecting malformed/truncated files.
    offset=8;ended=False;compressed=b''
    color=data[25];channels={0:1,2:3,4:2,6:4}.get(color)
    if data[24]!=8 or not channels or any(data[26:29]):raise ValueError('Unsupported PNG format.')
    while offset+12<=len(data):
     n=struct.unpack('>I',data[offset:offset+4])[0];end=offset+n+12
     if end>len(data) or zlib.crc32(data[offset+4:end-4])&0xffffffff!=struct.unpack('>I',data[end-4:end])[0]:raise ValueError('Invalid PNG data.')
     if data[offset+4:offset+8]==b'IDAT':compressed+=data[offset+8:end-4]
     if data[offset+4:offset+8]==b'IEND':ended=True;break
     offset=end
    if not ended:raise ValueError('Invalid PNG data.')
    try:
     expected=(1+width*channels)*height;decoder=zlib.decompressobj();pixels=decoder.decompress(compressed,expected+1)
     if len(pixels)!=expected or not decoder.eof or decoder.unconsumed_tail:raise ValueError('Invalid PNG data.')
    except zlib.error:raise ValueError('Invalid PNG data.')
    c.execute('INSERT OR IGNORE INTO profiles(owner) VALUES(?)',(uid,));c.execute('UPDATE profiles SET avatar=? WHERE owner=?',(value,uid));message='Profile image saved.';target=uid
   elif action=='profile_vote':
    if target==uid or m.get('price') not in (-1,0,1):raise ValueError('Choose another player to rate.')
    self.profile(c,target,uid);c.execute('INSERT OR REPLACE INTO profile_votes VALUES(?,?,?)',(target,uid,m['price']));message='Rating saved.'
   elif action=='profile_comment':
    self.profile(c,target,uid);value=m.get('value','')
    if not isinstance(value,str) or not 1<=len(value.strip())<=500:raise ValueError('Write 1–500 characters.')
    last=c.execute('SELECT MAX(created) FROM profile_comments WHERE author=?',(uid,)).fetchone()[0]
    if last and time.time()-last<10:raise ValueError('Wait a few seconds before commenting again.')
    c.execute('INSERT INTO profile_comments(owner,author,body,created) VALUES(?,?,?,?)',(target,uid,value.strip(),time.time()));message='Comment posted.'
   elif action=='comment_delete':
    if not c.execute('DELETE FROM profile_comments WHERE id=? AND (owner=? OR author=?)',(m.get('item'),uid,uid)).rowcount:raise ValueError('Comment unavailable.')
    message='Comment deleted.'
   elif action=='mission_claim':
    mission=next((x for x in MISSIONS if x['id']==target),None)
    if not mission or not c.execute('UPDATE quests SET claimed=1 WHERE owner=? AND quest=? AND period=? AND progress>=? AND claimed=0',(uid,target,period(mission),mission['goal'])).rowcount:raise ValueError('Mission is incomplete or already claimed.')
    c.execute('UPDATE career SET xp=xp+?,stars=stars+2 WHERE owner=?',(mission['xp'],uid));message='Mission claimed: +'+str(mission['xp'])+' XP, +2 stars.'
   elif action=='pass_buy':
    if c.execute('SELECT gold FROM career WHERE owner=?',(uid,)).fetchone()[0]:raise ValueError('Gold Pass already active.')
    self._spend_coins(c,uid,1000);c.execute('UPDATE career SET gold=1 WHERE owner=?',(uid,));message='Gold Pass activated.'
   elif action=='pass_levels':
    self._spend_coins(c,uid,500);c.execute('UPDATE career SET xp=xp+5000 WHERE owner=?',(uid,));message='Added 5 levels.'
   elif action=='pass_claim':
    match=re.fullmatch(r'(free|gold):(\d+)',target)
    if not match:raise ValueError('Reward unavailable.')
    tier,level=match[1],int(match[2]);progress=c.execute('SELECT * FROM career WHERE owner=?',(uid,)).fetchone()
    if not 1<=level<=30 or 1+progress['xp']//1000<level or tier=='gold' and not progress['gold']:raise ValueError('Unlock this reward first.')
    if not c.execute('INSERT OR IGNORE INTO pass_claims VALUES(?,?)',(uid,target)).rowcount:raise ValueError('Reward already claimed.')
    if tier=='gold':reward=self.grant(c,uid,self.arsenal[(level-1)%len(self.arsenal)]['contents'][(level-1)%len(self.arsenal[(level-1)%len(self.arsenal)]['contents'])])
    elif level%5==0:reward=self.grant(c,uid,'case:grand_case')
    else:c.execute('UPDATE accounts SET coins=coins+100 WHERE id=?',(uid,))
    message='Reward claimed.'
   elif action=='arsenal_stars':self._spend_coins(c,uid,500);c.execute('UPDATE career SET stars=stars+5 WHERE owner=?',(uid,));message='Added 5 Arsenal stars.'
   elif action=='arsenal_buy':
    collection=next((x for x in self.arsenal if x['id']==target),None)
    if not collection:raise ValueError('Collection unavailable.')
    if not c.execute('UPDATE career SET stars=stars-? WHERE owner=? AND stars>=?',(collection['price'],uid,collection['price'])).rowcount:raise ValueError('Not enough Arsenal stars.')
    reward=self.grant(c,uid,secrets.choice(collection['contents']));message='Collection purchased.'
   self.audit(c,uid,action,target)
  return message,reward,target if action.startswith('profile') or action=='comment_delete' else uid
 def _spend_coins(self,c,uid,price):
  if not c.execute('UPDATE accounts SET coins=coins-? WHERE id=? AND coins>=?',(price,uid,price)).rowcount:raise ValueError('Not enough coins.')
 def community_state(self,c,uid,view=None):
  self._career(c,uid);p=self.profile(c,view or uid,uid,read_only=True);career=dict(c.execute('SELECT * FROM career WHERE owner=?',(uid,)).fetchone());missions=[]
  for m in MISSIONS:
   row=c.execute('SELECT progress,claimed FROM quests WHERE owner=? AND quest=? AND period=?',(uid,m['id'],period(m))).fetchone();missions.append({**m,'progress':row[0] if row else 0,'claimed':bool(row[1]) if row else False})
  return dict(profile=p,progression={**career,'level':1+career['xp']//1000,'missions':missions,'claims':[r[0] for r in c.execute('SELECT reward FROM pass_claims WHERE owner=?',(uid,))],'collections':self.arsenal},leaderboard=[dict(r) for r in c.execute('SELECT a.id,a.name,c.rating,c.kills,c.matches,c.wins,c.deaths,p.avatar AS avatar FROM career c JOIN accounts a ON a.id=c.owner LEFT JOIN profiles p ON p.owner=a.id ORDER BY c.rating DESC,c.owner LIMIT 100')])
