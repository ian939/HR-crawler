import time
import random
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

def get_driver():
    options = Options()
    options.add_argument("--headless")  # GitHub Actions 등 서버 환경용
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

def crawl():
    # 수집 대상 기업 리스트
    companies = ["워터", "대영채비", "이브이시스", "플러그링크", "볼트업", "차지비", "에버온"]
    results = []
    driver = get_driver()

    for company in companies:
        print(f"--- {company} 수집 중 ---")
        
        # 1. 사람인 (Saramin)
        try:
            driver.get(f"https://www.saramin.co.kr/zf_user/search/recruit?searchword={company}")
            time.sleep(random.uniform(3, 5))
            items = driver.find_elements(By.CSS_SELECTOR, ".item_recruit")
            for item in items:
                title_el = item.find_element(By.CSS_SELECTOR, ".job_tit a")
                corp_el = item.find_element(By.CSS_SELECTOR, ".corp_name a")
                if company in corp_el.text:
                    results.append({
                        'site': '사람인', 
                        'company': corp_el.text.strip(), 
                        'title': title_el.text.strip(), 
                        'link': title_el.get_attribute('href')
                    })
        except Exception as e:
            print(f"사람인 {company} 오류: {e}")

        # 2. 원티드 (Wanted)
        try:
            driver.get(f"https://www.wanted.co.kr/search?query={company}&tab=position")
            time.sleep(5) # 원티드는 로딩 대기 필수
            items = driver.find_elements(By.CSS_SELECTOR, '[data-cy="post-card"]')
            for item in items:
                title = item.find_element(By.CSS_SELECTOR, '.job-card-title').text
                corp = item.find_element(By.CSS_SELECTOR, '.job-card-company-name').text
                link = item.find_element(By.TAG_NAME, 'a').get_attribute('href')
                if company in corp:
                    results.append({
                        'site': '원티드', 
                        'company': corp.strip(), 
                        'title': title.strip(), 
                        'link': link
                    })
        except Exception as e:
            print(f"원티드 {company} 오류: {e}")

        # 3. 잡코리아 (JobKorea) - 새로 추가됨
        try:
            driver.get(f"https://www.jobkorea.co.kr/Search/?stext={company}")
            time.sleep(random.uniform(3, 5))
            # 잡코리아 검색 결과 리스트 아이템 선택자
            items = driver.find_elements(By.CSS_SELECTOR, ".list-post .post")
            for item in items:
                title_el = item.find_element(By.CSS_SELECTOR, "a.title")
                corp_el = item.find_element(By.CSS_SELECTOR, "a.name")
                if company in corp_el.text:
                    results.append({
                        'site': '잡코리아', 
                        'company': corp_el.text.strip(), 
                        'title': title_el.text.strip(), 
                        'link': title_el.get_attribute('href')
                    })
        except Exception as e:
            print(f"잡코리아 {company} 오류: {e}")

    driver.quit()
    
    # 데이터 처리 및 저장
    if results:
        df = pd.DataFrame(results)
        # 중복 제거: 기업명과 제목이 완전히 같은 경우 1개만 남김
        df = df.drop_duplicates(subset=['company', 'title'], keep='first')
        # CSV 저장 (Excel 한글 깨짐 방지를 위해 utf-8-sig 사용)
        df.to_csv("jobs.csv", index=False, encoding='utf-8-sig')
        print(f"\n✅ 최종 성공: 총 {len(df)}건 수집 및 jobs.csv 저장 완료.")
    else:
        print("\n❌ 수집된 데이터가 없습니다.")

if __name__ == "__main__":
    crawl()