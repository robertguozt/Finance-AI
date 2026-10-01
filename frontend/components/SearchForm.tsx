"use client";

import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/lable";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { Textarea } from "../components/ui/textarea";
import { Loader2, Zap } from "lucide-react";

import type {
  FinancialCondition,
  HoldingHorizon,
  InvestmentStyle,
  RiskTolerance,
  SearchFormState,
  Sector,
} from "../lib/types";

const FINANCIAL_CONDITION_OPTIONS: {
  value: FinancialCondition;
  label: string;
}[] = [
  { value: "stable_income", label: "Stable income" },
  { value: "variable_income", label: "Variable income" },
  { value: "high_debt", label: "High debt" },
  { value: "emergency_fund", label: "Emergency fund available" },
];

const SECTOR_OPTIONS: Sector[] = [
  "Technology",
  "Finance",
  "Healthcare",
  "Consumer",
  "Energy",
  "Industrial",
];

interface SearchFormProps {
  formState: SearchFormState;
  setFormState: (
    update: (prevState: SearchFormState) => SearchFormState
  ) => void;
  handleSubmit: (e: React.FormEvent) => void;
  isLoading: boolean;
}

export function SearchForm({
  formState,
  setFormState,
  handleSubmit,
  isLoading,
}: SearchFormProps) {
  const handleChange = <K extends keyof SearchFormState>(
    key: K,
    value: SearchFormState[K]
  ) => {
    setFormState((prev) => ({
      ...prev,
      [key]: value,
    }));
  };

  const toggleFinancialCondition = (value: FinancialCondition) => {
    setFormState((prev) => ({
      ...prev,
      financialCondition: prev.financialCondition.includes(value)
        ? prev.financialCondition.filter((item) => item !== value)
        : [...prev.financialCondition, value],
    }));
  };

  const toggleSector = (value: Sector) => {
    setFormState((prev) => ({
      ...prev,
      preferredSectors: prev.preferredSectors.includes(value)
        ? prev.preferredSectors.filter((item) => item !== value)
        : [...prev.preferredSectors, value],
    }));
  };

  const handleExpectedReturnChange = (value: string) => {
    const parsedValue = Number(value);

    if (!Number.isFinite(parsedValue)) {
      handleChange("expectedReturn", 0);
      return;
    }

    const validatedValue = Math.min(100, Math.max(0, parsedValue));
    handleChange("expectedReturn", validatedValue);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Stock Ticker */}
      <div>
        <Label htmlFor="ticker">Stock Ticker</Label>
        <Input
          id="ticker"
          value={formState.ticker}
          onChange={(e) =>
            handleChange("ticker", e.target.value.toUpperCase())
          }
          placeholder="e.g., AAPL"
          required
        />
      </div>

      {/* Risk Tolerance */}
      <div>
        <Label htmlFor="riskTolerance">Risk Tolerance</Label>
        <Select
          value={formState.riskTolerance}
          onValueChange={(value) =>
            handleChange("riskTolerance", value as RiskTolerance)
          }
        >
          <SelectTrigger>
            <SelectValue placeholder="Select risk level" />
          </SelectTrigger>

          <SelectContent>
            <SelectItem value="Low">Low</SelectItem>
            <SelectItem value="Medium">Medium</SelectItem>
            <SelectItem value="High">High</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Expected Return */}
      <div>
        <Label htmlFor="expectedReturn">
          Expected Annual Return (%)
        </Label>

        <Input
          id="expectedReturn"
          type="number"
          min="0"
          max="100"
          step="1"
          value={formState.expectedReturn}
          onChange={(e) => handleExpectedReturnChange(e.target.value)}
          placeholder="e.g., 15"
          required
        />
      </div>

      {/* Financial Condition */}
      <fieldset>
        <legend className="mb-2 text-sm font-medium">
          Financial Condition
        </legend>

        <div className="space-y-2">
          {FINANCIAL_CONDITION_OPTIONS.map((option) => (
            <label
              key={option.value}
              className="flex items-center gap-2 text-sm"
            >
              <input
                type="checkbox"
                checked={formState.financialCondition.includes(
                  option.value
                )}
                onChange={() => toggleFinancialCondition(option.value)}
              />

              {option.label}
            </label>
          ))}

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={formState.hasOtherFinancialCondition}
              onChange={(e) =>
                handleChange(
                  "hasOtherFinancialCondition",
                  e.target.checked
                )
              }
            />

            Other
          </label>
        </div>

        {formState.hasOtherFinancialCondition && (
          <div className="mt-3">
            <Label htmlFor="financialConditionOther">
              Additional financial context
            </Label>

            <Textarea
              id="financialConditionOther"
              rows={3}
              maxLength={300}
              value={formState.financialConditionOther}
              onChange={(e) =>
                handleChange(
                  "financialConditionOther",
                  e.target.value
                )
              }
              placeholder="For example: I have irregular income and student-loan payments."
            />
          </div>
        )}
      </fieldset>

      {/* Preferred Sectors */}
      <fieldset>
        <legend className="mb-2 text-sm font-medium">
          Preferred Sectors
        </legend>

        <div className="grid grid-cols-2 gap-2">
          {SECTOR_OPTIONS.map((sector) => (
            <label
              key={sector}
              className="flex items-center gap-2 text-sm"
            >
              <input
                type="checkbox"
                checked={formState.preferredSectors.includes(sector)}
                onChange={() => toggleSector(sector)}
              />

              {sector}
            </label>
          ))}
        </div>
      </fieldset>

      {/* Investment Style */}
      <div>
        <Label htmlFor="investmentStyle">Investment Style</Label>

        <Select
          value={formState.investmentStyle}
          onValueChange={(value) =>
            handleChange("investmentStyle", value as InvestmentStyle)
          }
        >
          <SelectTrigger>
            <SelectValue placeholder="Select investment style" />
          </SelectTrigger>

          <SelectContent>
            <SelectItem value="growth">Growth</SelectItem>
            <SelectItem value="balanced">Balanced</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Holding Horizon */}
      <div>
        <Label htmlFor="holdingHorizon">Holding Horizon</Label>

        <Select
          value={formState.holdingHorizon}
          onValueChange={(value) =>
            handleChange("holdingHorizon", value as HoldingHorizon)
          }
        >
          <SelectTrigger>
            <SelectValue placeholder="Select holding period" />
          </SelectTrigger>

          <SelectContent>
            <SelectItem value="short">Short term</SelectItem>
            <SelectItem value="medium">Medium term</SelectItem>
            <SelectItem value="long">Long term</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Free-text notes for AI analysis */}
      <div>
        <Label htmlFor="tradingPreferences">
          Additional Preferences
        </Label>

        <Textarea
          id="tradingPreferences"
          rows={4}
          value={formState.tradingPreferences}
          onChange={(e) =>
            handleChange("tradingPreferences", e.target.value)
          }
          placeholder="For example: I prefer companies with strong AI exposure, but want to avoid highly leveraged businesses."
        />
      </div>

      {/* Submit Button */}
      <div>
        <Button
          type="submit"
          disabled={isLoading}
          className="w-full"
        >
          {isLoading ? (
            <Loader2 className="animate-spin h-5 w-5" />
          ) : (
            <Zap className="h-5 w-5 mr-2" />
          )}

          {isLoading ? "Analyzing..." : "Analyze"}
        </Button>
      </div>
    </form>
  );
}