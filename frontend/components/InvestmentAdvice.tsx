"use client";
import { Target, DollarSign, TrendingUp, TrendingDown } from "lucide-react";
// --- FIX: Using relative path to import the type from page.tsx ---
import type { InvestmentAdviceData } from "../lib/types";

// This is a placeholder.
export function InvestmentAdvice({ data }: { data: InvestmentAdviceData }) {
  
  // Handle cases where data might be null or undefined initially
  const entryPoint = data?.entryPoint ?? 0;
  const expectedReturn = data?.expectedReturn ?? 0;
  const stopLoss = data?.stopLoss ?? 0;

  return (
    <div className="bg-white dark:bg-gray-900 p-6 rounded-lg shadow-lg">
      <h3 className="text-xl font-semibold mb-4 text-gray-900 dark:text-white flex items-center">
        <Target className="h-6 w-6 mr-2 text-green-500" />
        AI Investment Advice
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Entry Point */}
        <div className="bg-gray-100 dark:bg-gray-800 p-4 rounded-lg flex items-center">
          <div className="p-3 rounded-full bg-blue-100 dark:bg-blue-900 mr-4">
            <DollarSign className="h-6 w-6 text-blue-500" />
          </div>
          <div>
            <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Entry Point</p>
            <p className="text-2xl font-bold text-gray-900 dark:text-white">${entryPoint.toFixed(2)}</p>
          </div>
        </div>
        {/* Expected Return */}
        <div className="bg-gray-100 dark:bg-gray-800 p-4 rounded-lg flex items-center">
          <div className="p-3 rounded-full bg-green-100 dark:bg-green-900 mr-4">
            <TrendingUp className="h-6 w-6 text-green-500" />
          </div>
          <div>
            <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Expected Return</p>
            <p className="text-2xl font-bold text-gray-900 dark:text-white">{expectedReturn.toFixed(1)}%</p>
          </div>
        </div>
        {/* Stop Loss */}
        <div className="bg-gray-100 dark:bg-gray-800 p-4 rounded-lg flex items-center">
          <div className="p-3 rounded-full bg-red-100 dark:bg-red-900 mr-4">
            <TrendingDown className="h-6 w-6 text-red-500" />
          </div>
          <div>
            <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Stop Loss</p>
            <p className="text-2xl font-bold text-gray-900 dark:text-white">${stopLoss.toFixed(2)}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
