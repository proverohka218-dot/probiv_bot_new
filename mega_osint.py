import aiohttp
import asyncio
import re
import random
from typing import Dict, List
from config import API_KEYS

class MegaOSINT:
    def __init__(self):
        self.session = None
        self.keys = API_KEYS
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, *args):
        await self.session.close()
    
    # ===== 1. TRUECALLER (есть ключ — использует официальный API, нет — бесплатный обход) =====
    async def truecaller_lookup(self, phone: str) -> Dict:
        if self.keys.get('truecaller'):
            url = f"https://api.truecaller.com/v1/search?phone={phone}"
            headers = {"Authorization": f"Bearer {self.keys['truecaller']}"}
            try:
                async with self.session.get(url, headers=headers, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {'name': data.get('name', '—'), 'country': data.get('countryCode', '—'),
                                'carrier': data.get('carrier', '—'), 'spam': data.get('spam', False)}
            except:
                pass
        
        # Fallback: бесплатный обход
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
    
    # ===== 2. NUMVERIFY / VERIPHONE =====
    async def numverify_lookup(self, phone: str) -> Dict:
        if self.keys.get('numverify'):
            url = f"http://apilayer.net/api/validate?access_key={self.keys['numverify']}&number={phone}&format=1"
            try:
                async with self.session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {'valid': data.get('valid', False), 'country': data.get('country_name', '—'),
                                'location': data.get('location', '—'), 'carrier': data.get('carrier', '—')}
            except:
                pass
        
        # Fallback: Veriphone с подменой IP
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
    
    # ===== 3. TELEGRAM =====
    async def telegram_lookup(self, phone: str = None, username: str = None) -> Dict:
        result = {'exists': False}
        try:
            from config import BOT_TOKEN
            if phone:
                clean = re.sub(r'[\s\(\)\-+]', '', phone)
                if not clean.startswith('+'):
                    clean = '+7' + clean if clean.startswith('7') else '+7' + clean
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChat?chat_id={clean}"
            elif username:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChat?chat_id=@{username}"
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
    
    # ===== 4. VK API =====
    # Поиск по ФИО / нику
    async def vk_search(self, query: str) -> List[Dict]:
        if self.keys.get('vk'):
            url = "https://api.vk.com/method/users.search"
            params = {
                'q': query,
                'access_token': self.keys['vk'],
                'v': '5.131',
                'count': 5
            }
            try:
                async with self.session.get(url, params=params, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('response', {}).get('items', [])
            except:
                pass
        
        url = f"https://api.vk.com/method/users.search?q={query}&v=5.131&count=5"
        try:
            async with self.session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('response', {}).get('items', [])
        except:
            pass
        return []
    
    # ===== 5. VK SEARCH BY PHONE (НОВОЕ) =====
    async def vk_search_by_phone(self, phone: str) -> Dict:
        if not self.keys.get('vk'):
            return {'error': 'Нет VK_TOKEN в настройках'}
        
        # Очистка номера: VK принимает 10 цифр (без 7 в начале)
        clean_phone = re.sub(r'[^0-9]', '', phone)
        if len(clean_phone) == 11 and clean_phone.startswith('7'):
            clean_phone = clean_phone[1:]
        elif len(clean_phone) == 10 and not clean_phone.startswith('7'):
            clean_phone = '7' + clean_phone
        
        url = "https://api.vk.com/method/users.get"
        params = {
            'user_ids': clean_phone,
            'access_token': self.keys['vk'],
            'v': '5.131',
            'fields': 'first_name,last_name,domain,photo_200'
        }
        
        try:
            async with self.session.get(url, params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if 'response' in data and data['response']:
                        user = data['response'][0]
                        return {
                            'exists': True,
                            'id': user.get('id'),
                            'first_name': user.get('first_name'),
                            'last_name': user.get('last_name'),
                            'domain': user.get('domain'),
                            'photo': user.get('photo_200'),
                            'url': f"https://vk.com/{user.get('domain') or 'id' + str(user.get('id'))}"
                        }
        except Exception as e:
            return {'error': str(e)}
        
        return {'exists': False}
    
    # ===== 6. SHERLOCK =====
    async def sherlock_search(self, username: str) -> List[str]:
        try:
            from sherlock_project import sherlock
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, sherlock.sherlock, username)
            found = [site['name'] for site in result if site['status'] == 'FOUND']
            return found if found else ['Не найдено']
        except:
            pass
        
        platforms = ['GitHub', 'Twitter', 'Instagram', 'VK', 'Reddit', 'YouTube']
        found = []
        for p in platforms:
            url = f"https://{p.lower()}.com/{username}"
            try:
                async with self.session.get(url, timeout=3) as resp:
                    if resp.status == 200:
                        found.append(p)
            except:
                continue
        return found if found else ['Не найдено']
    
    # ===== 7. OPENOSINT =====
    async def openosint_search(self, query: str, qtype: str = 'username') -> Dict:
        try:
            from openosint import OpenOSINT
            osint = OpenOSINT()
            if qtype == 'username':
                return osint.search_username(query)
            elif qtype == 'email':
                return osint.search_email(query)
            elif qtype == 'phone':
                return osint.search_phone(query)
        except:
            pass
        return {'error': 'openosint не установлен'}
    
    # ===== 8. HUNTER.IO =====
    async def hunter_verify(self, email: str) -> Dict:
        if self.keys.get('hunter'):
            url = f"https://api.hunter.io/v2/email-verifier?email={email}&api_key={self.keys['hunter']}"
            try:
                async with self.session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('data', {})
            except:
                pass
        return {'status': 'unknown', 'score': 0}
    
    # ===== 9. DEHASHED =====
    async def dehashed_search(self, query: str, qtype: str = 'email') -> List[Dict]:
        if self.keys.get('dehashed_email') and self.keys.get('dehashed_api'):
            url = f"https://api.dehashed.com/search?query={qtype}:{query}"
            auth = aiohttp.BasicAuth(self.keys['dehashed_email'], self.keys['dehashed_api'])
            try:
                async with self.session.get(url, auth=auth, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('entries', [])[:10]
            except:
                pass
        return []
    
    # ===== 10. EMAILREP =====
    async def emailrep_check(self, email: str) -> Dict:
        if self.keys.get('emailrep'):
            url = f"https://emailrep.io/{email}"
            headers = {"Authorization": f"Bearer {self.keys['emailrep']}"}
            try:
                async with self.session.get(url, headers=headers, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {'reputation': data.get('reputation', 'unknown'),
                                'suspicious': data.get('suspicious', False),
                                'malicious': data.get('malicious', False)}
            except:
                pass
        return {'reputation': 'unknown', 'suspicious': False, 'malicious': False}
    
    # ===== 11. IP2LOCATION =====
    async def ip2location(self, ip: str) -> Dict:
        if self.keys.get('ip2location'):
            url = f"https://api.ip2location.io/?ip={ip}&key={self.keys['ip2location']}"
            try:
                async with self.session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {'city': data.get('city', '—'), 'region': data.get('region', '—'),
                                'country': data.get('country_name', '—'), 'isp': data.get('isp', '—'),
                                'lat': data.get('latitude', 0), 'lon': data.get('longitude', 0)}
            except:
                pass
        
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
    
    # ===== 12. ABUSEIPDB =====
    async def abuseipdb(self, ip: str) -> Dict:
        if self.keys.get('abuseipdb'):
            url = f"https://api.abuseipdb.com/api/v2/check?ipAddress={ip}"
            headers = {"Key": self.keys['abuseipdb'], "Accept": "application/json"}
            try:
                async with self.session.get(url, headers=headers, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {'abuse_score': data['data'].get('abuseConfidenceScore', 0),
                                'total_reports': data['data'].get('totalReports', 0),
                                'country': data['data'].get('countryName', '—'),
                                'is_tor': data['data'].get('isTor', False)}
            except:
                pass
        
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
    
    # ===== 13. КОМБИНИРОВАННЫЙ ПОИСК =====
    async def full_search(self, phone: str = None, email: str = None, 
                          fio: str = None, username: str = None, ip: str = None) -> Dict:
        tasks = {}
        results = {}
        
        if phone:
            tasks['truecaller'] = self.truecaller_lookup(phone)
            tasks['numverify'] = self.numverify_lookup(phone)
            tasks['telegram'] = self.telegram_lookup(phone=phone)
            tasks['vk_search'] = self.vk_search(phone)
            tasks['vk_by_phone'] = self.vk_search_by_phone(phone)  # НОВОЕ
            tasks['openosint_phone'] = self.openosint_search(phone, 'phone')
        
        if email:
            tasks['hunter'] = self.hunter_verify(email)
            tasks['dehashed_email'] = self.dehashed_search(email, 'email')
            tasks['emailrep'] = self.emailrep_check(email)
            tasks['openosint_email'] = self.openosint_search(email, 'email')
        
        if username:
            tasks['telegram_username'] = self.telegram_lookup(username=username)
            tasks['sherlock'] = self.sherlock_search(username)
            tasks['vk_username'] = self.vk_search(username)
        
        if fio:
            tasks['vk_fio'] = self.vk_search(fio)
        
        if ip:
            tasks['ip2location'] = self.ip2location(ip)
            tasks['abuseipdb'] = self.abuseipdb(ip)
        
        for key, coro in tasks.items():
            try:
                results[key] = await coro
            except Exception as e:
                results[key] = {'error': str(e)}
        
        return results