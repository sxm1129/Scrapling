# Scraper Architecture Research Log
## Objective
Analyze and propose better, more reliable scraping strategies for all supported P0/P1 e-commerce platforms, moving away from brittle DOM evaluation toward robust API and App Protocol interception.

## Priority Platforms
1. Taobao / Tmall (淘宝/天猫)
2. JD Express (京东秒送)
3. Meituan Flash (美团闪购)
4. Douyin (抖音)
5. Pinduoduo & Fresh E-commerce (拼多多/社区团购)

## Analytical Scope
- Network interception vs DOM parsing
- Signature generation (x-sign, Anti-Content, mtgsig)
- State initialization via HTML embedded JSON
