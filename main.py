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
    # 페이지 로딩 최대 대기 시간 설정 (무한 대기 방지)
    driver.set_page_load_timeout(30)
    return driver

def extract_exp(text):
    """텍스트에서 경력 연차를 찾아 '경력N↑' 형태로 반환"""
    if not text: return "경력무관"
    
    # 'N년', 'N~M년' 형태 추출
    match = re.search(r'(\d+)년', text)
    if match:
        return f"경력{match.group(1)}↑"
    if "신입" in text:
        return "신입"
    return "경력무관"

def crawl():
    # '워터'는 노이즈 방지를 위해 포털 검색에서 제외 (공식홈 전용)
    companies = ["대영채비", "이브이시스", "플러그링크", "볼트업", "차지비", "에버온"]
    results = []
    driver = get_driver()

    # 1. 워터 공식 채용페이지 (BEP)
    print(">>> [워터] 공식홈페이지 수집 중...")
    try:
        driver.get("https://bep.co.kr/Career/recruitment?type=3")
        time.sleep(7)
        # 리스트 요소들을 광범위하게 수집
        items = driver.find_elements(By.CSS_SELECTOR, "div.recruitment-item, li, div[class*='item']")
        for item in items:
            t = item.text.strip().replace('\n', ' ')
            if any(k in t for k in ['매니저', '엔지니어', '팀장', '담당', '신입', '경력']):
                results.append({
                    'site': '공식홈', 'company': '워터(BEP)', 'title': t[:40],
                    'experience': extract_exp(t), 'link': driver.current_url
                })
    except: print("  - BEP 수집 실패")

    # 2. 포털 사이트 (사람인/원티드/잡코리아)
    for company in companies:
        print(f"\n>>> [{company}] 수집 시작")
        
        # [사람인]
        try:
            driver.get(f"https://www.saramin.co.kr/zf_user/search/recruit?searchword={company}")
            time.sleep(3)
            elements = driver.find_elements(By.CSS_SELECTOR, ".item_recruit")
            for el in elements[:10]:
                corp = el.find_element(By.CSS_SELECTOR, ".corp_name").text.strip()
                if company in corp:
                    title = el.find_element(By.CSS_SELECTOR, ".job_tit").text.strip()
                    # 경력 정보 추출 (조건 영역)
                    exp_info = el.find_element(By.CSS_SELECTOR, ".job_condition").text
                    results.append({
                        'site': '사람인', 'company': corp, 'title': title,
                        'experience': extract_exp(exp_info),
                        'link': el.find_element(By.CSS_SELECTOR, ".job_tit a").get_attribute('href')
                    })
        except: pass

        # [원티드]
        try:
            driver.get(f"https://www.wanted.co.kr/search?query={company}&tab=position")
            time.sleep(5)
            items = driver.find_elements(By.CSS_SELECTOR, '[data-cy="post-card"]')
            for item in items[:10]:
                corp = item.find_element(By.CSS_SELECTOR, '.job-card-company-name').text.strip()
                if company in corp:
                    title = item.find_element(By.CSS_SELECTOR, '.job-card-title').text.strip()
                    # 원티드는 카드 전체 텍스트에서 경력 유추
                    results.append({
                        'site': '원티드', 'company': corp, 'title': title,
                        'experience': extract_exp(item.text),
                        'link': item.find_element(By.TAG_NAME, 'a').get_attribute('href')
                    })
        except: pass

        # [잡코리아]
        try:
            driver.get(f"https://www.jobkorea.co.kr/Search/?stext={company}")
            time.sleep(5)
            posts = driver.find_elements(By.CSS_SELECTOR, ".list-post .post")
            for p in posts[:10]:
                corp = p.find_element(By.CSS_SELECTOR, ".name").text.strip()
                if company in corp:
                    title = p.find_element(By.CSS_SELECTOR, ".title").text.strip()
                    exp_info = p.find_element(By.CSS_SELECTOR, ".exp, .option").text
                    results.append({
                        'site': '잡코리아', 'company': corp, 'title': title,
                        'experience': extract_exp(exp_info),
                        'link': p.find_element(By.CSS_SELECTOR, "a.title").get_attribute('href')
                    })
        except: pass

    driver.quit()

    # 데이터 저장
    if results:
        df = pd.DataFrame(results).drop_duplicates(subset=['company', 'title'])
        # 날짜별 파일명 생성 (예: jobs_20251223.csv)
        filename = f"jobs_{datetime.now().strftime('%Y%m%d')}.csv"
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        print(f"\n✅ 완료: {filename} 저장 ({len(df)}건)")
    else:
        print("\n❌ 수집된 데이터 없음")

if __name__ == "__main__":
    crawl()
