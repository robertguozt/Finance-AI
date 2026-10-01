export type RiskTolerance = "Low" | "Medium" | "High";

export type FinancialCondition =
  | "stable_income"
  | "variable_income"
  | "high_debt"
  | "emergency_fund";

export type Sector =
  | "Technology"
  | "Finance"
  | "Healthcare"
  | "Consumer"
  | "Energy"
  | "Industrial";

export type InvestmentStyle = "growth" | "balanced";
export type HoldingHorizon = "short" | "medium" | "long";

export interface SearchFormState {
  ticker: string;
  financialCondition: FinancialCondition[];
  hasOtherFinancialCondition: boolean;
  financialConditionOther: string;
  expectedReturn: number;
  riskTolerance: RiskTolerance;
  preferredSectors: Sector[];
  investmentStyle: InvestmentStyle;
  holdingHorizon: HoldingHorizon;
  tradingPreferences: string;
}

export interface ForecastData {
  month: string;
  price: number;
  type: "history" | "forecast";
}

export interface InvestmentAdviceData {
  entryPoint: number;
  expectedReturn: number;
  stopLoss: number;
}

export interface RecommendedStockData {
  ticker: string;
  score: number;
  sector: string;
  reason: string;
  current_price: number;
  pe_ratio: number | null;
}

export interface AnalysisResult {
  forecastData: ForecastData[];
  investmentAdvice: InvestmentAdviceData;
  recommendedStocks: RecommendedStockData[];
  analysis: string;
  keyNews: string;
}
