"use client";

import { BarChart, Loader2 } from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription
} from "./ui/card"; 

import { ForecastData } from "../lib/types";

interface StockChartProps {
  data: ForecastData[];
}

export function StockChart({ data }: StockChartProps) {
  
  // 1. Handle Loading/Empty State
  if (!data || data.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center">
            <BarChart className="h-6 w-6 mr-2 text-indigo-500" />
            12-Month Price Forecast
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-72 flex items-center justify-center bg-gray-100 dark:bg-gray-800 rounded-md">
            <p className="text-gray-500 ml-3">Waiting for data...</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  // 2. Sanitize Data
  const sanitizedData = data.map(item => ({
    ...item,
    price: typeof item.price === 'string' ? parseFloat(item.price) : item.price,
    month: item.month || '?' 
  })).filter(item => !isNaN(item.price));
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center">
          <BarChart className="h-6 w-6 mr-2 text-indigo-500" />
          12-Month Price Forecast
        </CardTitle>
        <CardDescription>
          AI-generated price prediction for the next 12 months.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={sanitizedData} 
              margin={{
                top: 5,
                right: 30,
                left: 20,
                bottom: 5,
              }}
            >
              <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
              <XAxis 
                dataKey="month" 
                stroke="#9ca3af" 
                fontSize={12}
                interval="preserveStartEnd" 
              />
              <YAxis 
                stroke="#9ca3af" 
                fontSize={12}
                domain={['auto', 'auto']} 
                tickFormatter={(value) => `$${value}`}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#1f2937", 
                  borderColor: "#374151", 
                  borderRadius: "0.5rem",
                  color: "#f9fafb" 
                }}
                labelStyle={{ color: "#f9fafb" }}
                itemStyle={{ color: "#f9fafb" }}
                formatter={(value: any) => [`$${value}`, "Forecast Price"]}
              />
              <Legend />
              
              <Line
                type="monotone"
                dataKey="price"
                stroke="#a78bfa" // violet-400
                strokeWidth={3}
                name="Forecast"
                dot={{ r: 4, fill: "#a78bfa", strokeWidth: 0 }}
                activeDot={{ r: 6 }}
                isAnimationActive={true}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
