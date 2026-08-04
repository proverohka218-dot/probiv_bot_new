import aiohttp
import asyncio
import re
import random
from typing import Dict, List

class MegaOSINT:
    def __init__(self):
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, *args):
        await self.session.close()
    
    async def truecaller_lookup(self, phone: str) -> Dict:
        url = f"https://truecaller-api.vercel.app/api/search?phone={phone}"
        try:
            async with self.session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {'name': data.get('name', '—'), 'country': data.get('country', '—'),
                            'carrier': data.get('carrier', '—'), 'spam': data.get('spam', False)}
        except:
            pass
        return {'name': '—', 'country': '—', 'carrier': '—', 'spam': False}
    
    async def numverify_lookup(self, phone: str) -> Dict:
        fake_ip = f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
        url = f"https://api.veriphone.io/v2/verify?phone={phone}&default_country=RU"
        headers = {"X-Forwarded-For": fake_ip}
        try:
            async with self.session.get(url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {'valid': data.get('valid', False), 'country': data.get('country_name', '—'),
                            'location': data.get('location', '—'), 'carrier': data.get('carrier', '—')}
        except:
            pass
        return {'valid': False, 'country': '—', 'location': '—', 'carrier': '—'}
    
    async def hunter_verify(self, email: str) -> Dict:
        url = f"https://email-checker.net/api/verify?email={email}"
        try:
            async with self.session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {'status': data.get('status', 'unknown'), 'score': data.get('score', 0)}
        except:
            pass
        return {'status': 'unknown', 'score': 0}
    
    async def dehashed_search(self, query: str, qtype: str = 'email') -> List[Dict]:
        url = f"https://leak-check.net/api/public?query={query}&type={qtype}"
        try:
            async with self.session.get(url, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('results', [])[:10]
        except:
            pass
        return []
    
    async def ip2location(self, ip: str) -> Dict:
        url = f"http://ip-api.com/json/{ip}?fields=status,message,country,regionName,city,isp,lat,lon,timezone"
        try:
            async with self.session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {'city': data.get('city', '—'), 'region': data.get('regionName', '—'),
                            'country': data.get('country', '—'), 'isp': data.get('isp', '—'),
                            'lat': data.get('lat', 0), 'lon': data.get('lon', 0)}
        except:
            pass
        return {'city': '—', 'region': '—', 'country': '—', 'isp': '—'}
    
    async def abuseipdb(self, ip: str) -> Dict:
        url = f"https://api.iptoasn.com/v1/as/ip/{ip}"
        try:
            async with self.session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {'abuse_score': 0, 'total_reports': data.get('total_reports', 0),
                            'country': data.get('country', '—'), 'is_tor': False}
        except:
            pass
        return {'abuse_score': 0, 'total_reports': 0, 'country': '—', 'is_tor': False}
    
    async def telegram_lookup(self, phone: str = None, username: str = None) -> Dict:
        result = {'exists': False}
        try:
            if phone:
                clean = re.sub(r'[\s\(\)\-+]', '', phone)
                if not clean.startswith('+'):
                    clean = '+7' + clean if clean.startswith('7') else '+7' + clean
                url = f"https://api.telegram.org/bot{self.keys.get('telegram_bot', '')}/getChat?chat_id={clean}"
            elif username:
                url = f"https://api.telegram.org/bot{self.keys.get('telegram_bot', '')}/getChat?chat_id=@{username}"
            else:
                return result
            async with self.session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('ok'):
                        result['exists'] = True
                        result['username'] = data['result'].get('username', '—')
                        result['first_name'] = data['result'].get('first_name', '—')
        except:
            pass
        return result
    
    async def vk_search(self, query: str) -> List[Dict]:
        url = f"https://api.vk.com/method/users.search?q={query}&v=5.131&count=5"
        try:
            async with self.session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('response', {}).get('items', [])
        except:
            pass
        return []
    
    async def sherlock_search(self, username: str) -> List[str]:
        platforms = ['GitHub', 'Twitter', 'Instagram', 'VK', 'Reddit', 'YouTube', 'TikTok', 'Pinterest', 'Twitch']
        found = []
        tasks = []
        for p in platforms:
            url = f"https://{p.lower()}.com/{username}"
            tasks.append(self._check_platform(p, url))
        results = await asyncio.gather(*tasks)
        found = [p for p, ok in results if ok]
        return found if found else ['Не найдено']
    
    async def _check_platform(self, platform: str, url: str) -> tuple:
        try:
            async with self.session.get(url, timeout=3) as resp:
                if resp.status == 200:
                    return (platform, True)
        except:
            pass
        return (platform, False)
    
    async def hibp_check(self, email: str) -> Dict:
        result = {'breaches': [], 'count': 0}
        try:
            url = f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}"
            async with self.session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result['breaches'] = [b['Name'] for b in data[:5]]
                    result['count'] = len(data)
        except:
            pass
        return result
    
    async def full_search(self, phone: str = None, email: str = None, 
                          fio: str = None, username: str = None, ip: str = None) -> Dict:
        tasks = {}
        results = {}
        
        if phone:
            tasks['truecaller'] = self.truecaller_lookup(phone)
            tasks['numverify'] = self.numverify_lookup(phone)
            tasks['telegram_phone'] = self.telegram_lookup(phone=phone)
            tasks['dehashed_phone'] = self.dehashed_search(phone, 'phone')
        
        if email:
            tasks['hunter'] = self.hunter_verify(email)
            tasks['dehashed_email'] = self.dehashed_search(email, 'email')
            tasks['hibp'] = self.hibp_check(email)
        
        if fio:
            tasks['vk_fio'] = self.vk_search(fio)
        
        if username:
            tasks['telegram_username'] = self.telegram_lookup(username=username)
            tasks['sherlock'] = self.sherlock_search(username)
            tasks['vk_username'] = self.vk_search(username)
        
        if ip:
            tasks['ip2location'] = self.ip2location(ip)
            tasks['abuseipdb'] = self.abuseipdb(ip)
        
        for key, coro in tasks.items():
            try:
                results[key] = await coro
            except Exception as e:
                results[key] = {'error': str(e)}
        
        return results