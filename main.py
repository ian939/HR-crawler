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
    """텍스트에서 경력 연차 추출. 없으면 None(null) 반환"""
    if not text: return None
    match = re.search(r'(\d+)\s*년', text)
    if match:
        return f"경력{match.group(1)}↑"
    if "신입" in text:
        return "신입"
    if any(k in text for k in ["경력", "시니어", "주니어"]):
        return "경력"
    return None

def crawl_bep_official(driver):
    """'워터(BEP)' 공식홈페이지(type=3) 전용 수집 로직"""
    print(">>> [워터] 공식홈페이지 수집 시도...")
    url = "https://bep.co.kr/Career/recruitment?type=3"
    results = []
    try:
        driver.get(url)
        # 페이지 로딩 및 리스트 렌더링을 위해 충분히 대기 (최대 15초)
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(10)
        
        # 1. '모집중' 텍스트를 포함하는 모든 요소 탐색 (XPATH 활용)
        # BEP 사이트의 구조적 유연성을 위해 broad하게 탐색 후 부모 요소(a 혹은 div)로 이동
        items = driver.find_elements(By.XPATH, "//*[contains(text(), '모집중')]/ancestor::a[1] | //*[contains(text(), '모집중')]/ancestor::div[contains(@class, 'item')][1]")
        
        if not items:
            # 2. XPATH로 실패할 경우 특정 클래스명 기반 재시도
            items = driver.find_elements(By.CSS_SELECTOR, "a.recruitment-item, .recruitment-list a")

        seen_titles = set()
        for item in items:
            raw_text = item.text.strip().replace('\n', ' ')
            # '모집중' 키워드를 제거하여 순수 제목만 추출
            title = raw_text.replace("모집중", "").strip()
            
            if title and title not in seen_titles:
                results.append({
                    'site': '공식홈',
                    'company': '워터(BEP)',
                    'title': title,
                    'experience': extract_exp(raw_text),
                    'link': url
                })
                seen_titles.add(title)
        
        print(f"  - 워터(BEP): {len(results)}건 수집됨.")
    except Exception as e:
        print(f"  - BEP 수집 중 오류: {e}")
    return results

def crawl_all():
    companies = ["대영채비", "이브이시스", "플러그링크", "볼트업", "차지비", "에버온"]
    results = []
    driver = get_driver()

    # 1. 워터 공식홈 수집 (최우선 실행)
    results.extend(crawl_bep_official(driver))

    # 2. 포털 사이트 수집
    for company in companies:
        print(f"\n>>> [{company}] 포털 수집 시작")
        
        # [사람인]
        try:
            driver.get(f"https://www.saramin.co.kr/zf_user/search/recruit?searchword={company}")
            time.sleep(5)
            elements = driver.find_elements(By.CSS_SELECTOR, ".item_recruit")
            for el in elements[:10]:
                corp = el.find_element(By.CSS_SELECTOR, ".corp_name").text.strip()
                if company in corp:
                    title_el = el.find_element(By.CSS_SELECTOR, ".job_tit a")
                    cond = el.find_element(By.CSS_SELECTOR, ".job_condition").text
                    results.append({
                        'site': '사람인', 'company': corp, 'title': title_el.text.strip(),
                        'experience': extract_exp(cond),
                        'link': title_el.get_attribute('href')
                    })
        except: pass

        # [원티드]
        try:
            driver.get(f"https://www.wanted.co.kr/search?query={company}&tab=position")
            time.sleep(7)
            cards = driver.find_elements(By.CSS_SELECTOR, '[data-cy="post-card"]')
            for card in cards[:10]:
                corp = card.find_element(By.CSS_SELECTOR, '.job-card-company-name').text.strip()
                if company in corp:
                    results.append({
                        'site': '원티드', 'company': corp, 'title': card.find_element(By.CSS_SELECTOR, '.job-card-title').text.strip(),
                        'experience': extract_exp(card.text),
                        'link': card.find_element(By.TAG_NAME, 'a').get_attribute('href')
                    })
        except: pass

        # [잡코리아]
        try:
            driver.get(f"https://www.jobkorea.co.kr/Search/?stext={company}")
            time.sleep(6)
            posts = driver.find_elements(By.CSS_SELECTOR, ".list-post .post")
            for p in posts[:10]:
                corp = p.find_element(By.CSS_SELECTOR, ".name").text.strip()
                if company in corp:
                    title_el = p.find_element(By.CSS_SELECTOR, "a.title")
                    try: exp_text = p.find_element(By.CSS_SELECTOR, ".exp, .option").text
                    except: exp_text = p.text
                    results.append({
                        'site': '잡코리아', 'company': corp, 'title': title_el.text.strip(),
                        'experience': extract_exp(exp_text),
                        'link': title_el.get_attribute('href')
                    })
        except: pass

    driver.quit()

    if results:
        df = pd.DataFrame(results).drop_duplicates(subset=['company', 'title'])
        df = df[['site', 'company', 'title', 'experience', 'link']]
        
        # 파일명을 당일 날짜로 설정
        filename = f"jobs_{datetime.now().strftime('%Y%m%d')}.csv"
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        print(f"\n✅ 최종 완료: {filename} 저장됨 (총 {len(df)}건)")
    else:
        print("\n❌ 수집된 데이터가 없습니다.")

if __name__ == "__main__":
    crawl_all()
