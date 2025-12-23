import time
import re
import random
from datetime import datetime
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

def get_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.set_page_load_timeout(60)
    return driver

def extract_exp(text):
    """텍스트에서 경력 정보를 정밀하게 추출하여 '경력N↑' 등으로 반환"""
    if not text: return None
    
    # 1. 'N년', 'N~M년' 패턴 추출
    match = re.search(r'(\d+)\s*년', text)
    if match:
        return f"경력{match.group(1)}↑"
    
    # 2. '신입' 키워드
    if "신입" in text:
        return "신입"
    
    # 3. 숫자가 없는 '경력' 키워드 (예: HR(경력))
    if "경력" in text or "시니어" in text:
        return "경력"
    
    # 4. '주니어' 키워드
    if "주니어" in text:
        return "주니어"
        
    return None # 정보가 없으면 명시적으로 null(None) 반환

def crawl_bep_official(driver):
    """'워터' 공식홈페이지(type=3) 전용 수집 로직"""
    print(">>> [워터] 공식홈페이지(전기차충전) 수집 중...")
    url = "https://bep.co.kr/Career/recruitment?type=3"
    results = []
    try:
        driver.get(url)
        # 페이지 로딩 및 리스트 렌더링 대기
        time.sleep(10)
        
        # '모집중' 텍스트를 포함하는 링크(a) 또는 디비전(div)을 직접 타겟팅
        items = driver.find_elements(By.XPATH, "//*[contains(text(), '모집중')]/ancestor-or-self::*[self::a or self::div][position()=1]")
        
        seen_titles = set()
        for item in items:
            raw_text = item.text.strip().replace('\n', ' ')
            # '모집중' 단어를 제외한 실제 직무 타이틀 추출
            title = raw_text.replace("모집중", "").strip()
            
            if title and title not in seen_titles:
                results.append({
                    'site': '공식홈',
                    'company': '워터(BEP)',
                    'title': title,
                    'experience': extract_exp(raw_text), # 텍스트에서 경력 추출 시도
                    'link': url
                })
                seen_titles.add(title)
        
        print(f"  - 워터(BEP): {len(results)}건 수집 완료 (목표: 5건)")
    except Exception as e:
        print(f"  - BEP 수집 중 오류: {e}")
    return results

def crawl_all():
    # 포털 검색 대상 기업 (워터는 공식홈에서만 수집하므로 제외)
    companies = ["대영채비", "이브이시스", "플러그링크", "볼트업", "차지비", "에버온"]
    results = []
    driver = get_driver()

    # 1. 워터 공식홈 수집 (최우선)
    results.extend(crawl_bep_official(driver))

    # 2. 나머지 포털 사이트 수집 (사람인/원티드/잡코리아)
    for company in companies:
        print(f"\n>>> [{company}] 수집 시작")
        
        # [사람인]
        try:
            driver.get(f"https://www.saramin.co.kr/zf_user/search/recruit?searchword={company}")
            time.sleep(5)
            # 사람인 공고 아이템 영역
            items = driver.find_elements(By.CSS_SELECTOR, ".item_recruit")
            for item in items[:15]:
                corp = item.find_element(By.CSS_SELECTOR, ".corp_name").text.strip()
                if company in corp:
                    title_el = item.find_element(By.CSS_SELECTOR, ".job_tit a")
                    title = title_el.text.strip()
                    # 경력 정보가 있는 .job_condition 텍스트 수집
                    condition = item.find_element(By.CSS_SELECTOR, ".job_condition").text
                    results.append({
                        'site': '사람인', 'company': corp, 'title': title,
                        'experience': extract_exp(condition),
                        'link': title_el.get_attribute('href')
                    })
        except: pass

        # [원티드]
        try:
            driver.get(f"https://www.wanted.co.kr/search?query={company}&tab=position")
            time.sleep(7)
            cards = driver.find_elements(By.CSS_SELECTOR, '[data-cy="post-card"]')
            for card in cards[:15]:
                corp = card.find_element(By.CSS_SELECTOR, '.job-card-company-name').text.strip()
                if company in corp:
                    title = card.find_element(By.CSS_SELECTOR, '.job-card-title').text.strip()
                    results.append({
                        'site': '원티드', 'company': corp, 'title': title,
                        'experience': extract_exp(card.text),
                        'link': card.find_element(By.TAG_NAME, 'a').get_attribute('href')
                    })
        except: pass

        # [잡코리아]
        try:
            driver.get(f"https://www.jobkorea.co.kr/Search/?stext={company}")
            time.sleep(6)
            posts = driver.find_elements(By.CSS_SELECTOR, ".list-post .post")
            for post in posts[:15]:
                corp = post.find_element(By.CSS_SELECTOR, ".name").text.strip()
                if company in corp:
                    title_el = post.find_element(By.CSS_SELECTOR, "a.title")
                    title = title_el.text.strip()
                    try:
                        exp_info = post.find_element(By.CSS_SELECTOR, ".exp, .option").text
                    except: exp_info = post.text
                    results.append({
                        'site': '잡코리아', 'company': corp, 'title': title,
                        'experience': extract_exp(exp_info),
                        'link': title_el.get_attribute('href')
                    })
        except: pass

    driver.quit()

    if results:
        df = pd.DataFrame(results).drop_duplicates(subset=['company', 'title'])
        # 컬럼 순서 고정
        df = df[['site', 'company', 'title', 'experience', 'link']]
        
        # 파일명을 날짜별로 생성 (예: jobs_20251223.csv)
        filename = f"jobs_{datetime.now().strftime('%Y%m%d')}.csv"
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        print(f"\n✅ 수집 성공: {filename} 저장 ({len(df)}건)")
    else:
        print("\n❌ 데이터 수집 실패: 수집된 결과가 없습니다.")

if __name__ == "__main__":
    crawl_all()
