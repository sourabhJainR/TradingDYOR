from dataclasses import dataclass

@dataclass(frozen=True)
class Source:
    name: str
    url: str
    category: str = "research"

SOURCES = [
    Source("Dataroma","https://www.dataroma.com/"),
    Source("WhaleWisdom","https://whalewisdom.com/"),
    Source("Capitol Trades","https://www.capitoltrades.com/"),
    Source("OpenInsider","https://openinsider.com/"),
    Source("SEC EDGAR","https://www.sec.gov/edgar/search/"),
    Source("Berkshire Hathaway Letters","https://www.berkshirehathaway.com/letters/letters.html"),
    Source("Buffett CNBC","https://www.cnbc.com/warren-buffett/"),
    Source("Oaktree","https://www.oaktreecapital.com/insights"),
    Source("Bridgewater","https://www.bridgewater.com/research-and-insights"),
    Source("GMO","https://www.gmo.com/americas/research-library/"),
    Source("AQR","https://www.aqr.com/Insights"),
    Source("Damodaran","https://pages.stern.nyu.edu/~adamodar/"),
    Source("Collaborative Fund","https://collabfund.com/blog/"),
    Source("Farnam Street","https://fs.blog/"),
    Source("JPM Guide to the Markets","https://am.jpmorgan.com/us/en/asset-management/adv/insights/market-insights/guide-to-the-markets/"),
    Source("ARK","https://www.ark-invest.com/"),
    Source("Paul Graham","https://paulgraham.com/articles.html"),
    Source("CS Investing","https://csinvesting.org/"),
    Source("Columbia Value Investing","https://www8.gsb.columbia.edu/valueinvesting/"),
    Source("FRED","https://fred.stlouisfed.org/"),
    Source("Federal Reserve","https://www.federalreserve.gov/"),
    Source("ECB","https://www.ecb.europa.eu/"),
    Source("BIS","https://www.bis.org/"),
    Source("World Bank","https://www.worldbank.org/"),
    Source("Macrotrends","https://www.macrotrends.net/"),
    Source("GuruFocus","https://www.gurufocus.com/"),
    Source("CompaniesMarketCap","https://companiesmarketcap.com/"),
    Source("Finviz","https://finviz.com/"),
    Source("Portfolio Visualizer","https://www.portfoliovisualizer.com/"),
    Source("TradingView","https://www.tradingview.com/"),
    Source("Koyfin","https://www.koyfin.com/"),
    Source("Investor.gov","https://www.investor.gov/"),
    Source("Bogleheads","https://www.bogleheads.org/"),
    Source("Investopedia","https://www.investopedia.com/"),
    Source("State Street","https://www.ssga.com/us/en/intermediary/insights"),
    Source("CFA Institute","https://rpc.cfainstitute.org/"),
    Source("Morningstar","https://www.morningstar.com/"),
    Source("Visual Capitalist","https://www.visualcapitalist.com/"),
    Source("ARK Intel","https://ark-invest.com/innovation-whitepapers/"),
    Source("Holdings Channel","https://www.holdingschannel.com/"),
    Source("justETF","https://www.justetf.com/"),
    Source("Alpha Architect","https://alphaarchitect.com/"),
    Source("Shiller Data","https://shillerdata.com/"),
    Source("Behavioral Investment","https://behavioralinvestment.com/"),
    Source("Our World in Data","https://ourworldindata.org/"),
    Source("Our Finite World","https://ourfiniteworld.com/"),
    Source("SEC Company Search","https://www.sec.gov/edgar/searchedgar/companysearch"),
    Source("SEC Filings Search","https://www.sec.gov/edgar/search/"),
]

SOURCES.extend([
    Source("SEC Form 13F Data Sets","institutional","https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets"),
    Source("FRED API","macro","https://fred.stlouisfed.org/docs/api/fred/overview.html"),
    Source("USPTO Open Data","patents","https://developer.uspto.gov/"),
])
