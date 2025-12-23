import time
import random
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
    # GitHub Actions와 로컬 환경 모두 대응
    options.add_argument("--headless") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

def crawl_bep_official(driver):
    """'워터' 공식 채용 페이지(bep.co.kr) 수집"""
    print("--- [워터] 공식 홈페이지 수집 시도 ---")
    url = "https://bep.co.kr/Career/recruitment?type=3"
    results = []
    try:
        driver.get(url)
        # BEP 사이트는 로딩 시간이 필요함 (최대 15초 대기)
        wait = WebDriverWait(driver, 15)
        # 공고 리스트가 포함된 섹션이 나타날 때까지 대기
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(5) # 스크립트 실행 대기 추가
        
        # BEP 사이트의 텍스트 기반 수집 (구조가 유동적이므로 '채용' 관련 텍스트 검색)
        items = driver.find_elements(By.XPATH, "//*[contains(@class, 'title') or contains(@class, 'subject')]")
        
        for item in items:
            title = item.text.strip()
            if title and len(title) > 2: # 유효한 제목만 수집
                results.append({
                    'site': '공식홈',
                    'company': '워터(BEP)',
                    'title': title,
                    'link': url
                })
        print(f"  > 워터 공식홈: {len(results)}건 발견")
    except Exception as e:
        print(f"  > 워터 공식홈 수집 오류: {e}")
    return results

def crawl_portals():
    # '워터'는 노이즈 방지를 위해 포털 검색 리스트에서 제외
    companies = ["대영채비", "이브이시스", "플러그링크", "볼트업", "차지비", "에버온"]
    results = []
    driver = get_driver()

    # 1. 워터 공식홈 데이터 먼저 수집
    results.extend(crawl_bep_official(driver))

    for company in companies:
        print(f"--- {company} 포털 수집 시작 ---")
        
        # [사람인]
        try:
            driver.get(f"https://www.saramin.co.kr/zf_user/search/recruit?searchword={company}")
            time.sleep(random.uniform(3, 5))
            items = driver.find_elements(By.CSS_SELECTOR, ".item_recruit")
            for item in items:
                corp = item.find_element(By.CSS_SELECTOR, ".corp_name a").text.strip()
                if company in corp:
                    title_el = item.find_element(By.CSS_SELECTOR, ".job_tit a")
                    results.append({'site': '사람인', 'company': corp, 'title': title_el.text.strip(), 'link': title_el.get_attribute('href')})
        except: pass

        # [원티드] 차단 우회를 위한 대기 강화
        try:
            driver.get(f"https://www.wanted.co.kr/search?query={company}&tab=position")
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-cy="post-card"]')))
            time.sleep(3)
            items = driver.find_elements(By.CSS_SELECTOR, '[data-cy="post-card"]')
            for item in items:
                corp = item.find_element(By.CSS_SELECTOR, '.job-card-company-name').text.strip()
                if company in corp:
                    title = item.find_element(By.CSS_SELECTOR, '.job-card-title').text.strip()
                    link = item.find_element(By.TAG_NAME, 'a').get_attribute('href')
                    results.append({'site': '원티드', 'company': corp, 'title': title, 'link': link})
        except: pass

        # [잡코리아]
        try:
            driver.get(f"https://www.jobkorea.co.kr/Search/?stext={company}")
            time.sleep(5)
            # 잡코리아의 다양한 선택자 대응
            items = driver.find_elements(By.CSS_SELECTOR, ".list-post .post, .item, .list-item")
            for item in items:
                try:
                    corp = item.find_element(By.CSS_SELECTOR, ".name, .corp, .name a").text.strip()
                    if company in corp:
                        title_el = item.find_element(By.CSS_SELECTOR, ".title, .tit, a.title")
                        link = title_el.get_attribute('href')
                        results.append({'site': '잡코리아', 'company': corp, 'title': title_el.text.strip(), 'link': link})
                except: continue
        except: pass

    driver.quit()
    
    if results:
        df = pd.DataFrame(results)
        df = df.drop_duplicates(subset=['company', 'title'], keep='first')
        df.to_csv("jobs.csv", index=False, encoding='utf-8-sig')
        print(f"\n✅ 최종 {len(df)}건 수집 완료 (jobs.csv 저장)")
    else:
        print("\n❌ 수집된 데이터가 없습니다.")

if __name__ == "__main__":
    crawl_portals()
