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

// --- FIX: Changed path to be explicitly correct based on your folder structure ---
// Assuming your folder structure is:
// frontend/
//   components/
//     ui/
//       card.tsx
//     StockChart.tsx
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription
} from "../components/ui/card"; 

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

  // 2. Sanitize Data: Ensure prices are numbers and months exist
  const sanitizedData = data.map(item => ({
    ...item,
    price: typeof item.price === 'string' ? parseFloat(item.price) : item.price,
    month: item.month || '?' 
  })).filter(item => !isNaN(item.price));

  // 3. Split Data
  const historyData = sanitizedData.filter((d) => d.type === 'history');
  const forecastData = sanitizedData.filter((d) => d.type === 'forecast');

  // 4. Create Connector Line
  const connectorData: ForecastData[] = [];
  if (historyData.length > 0 && forecastData.length > 0) {
    connectorData.push(historyData[historyData.length - 1]);
    connectorData.push(forecastData[0]);
  }

  // 5. Handle Case: Only History (No Forecast returned)
  if (forecastData.length === 0 && historyData.length > 0) {
     return (
        <Card>
        <CardHeader>
          <CardTitle className="flex items-center">
            <BarChart className="h-6 w-6 mr-2 text-indigo-500" />
            12-Month Price Forecast
          </CardTitle>
          <CardDescription>
            Only historical data available. AI could not generate a forecast.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-72 w-full">
             <ResponsiveContainer width="100%" height="100%">
              <LineChart data={sanitizedData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
                <XAxis dataKey="month" stroke="#9ca3af" fontSize={12} />
                <YAxis stroke="#9ca3af" fontSize={12} domain={['auto', 'auto']} tickFormatter={(value) => `$${value}`} />
                <Tooltip contentStyle={{ backgroundColor: "#1f2937", borderColor: "#374151", borderRadius: "0.5rem", color: "#f9fafb" }} />
                <Legend />
                <Line type="monotone" dataKey="price" stroke="#4f46e5" strokeWidth={2} name="Historical" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>
     )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center">
          <BarChart className="h-6 w-6 mr-2 text-indigo-500" />
          12-Month Price Forecast
        </CardTitle>
        <CardDescription>
          AI-generated 12-month price trend based on fundamentals and news sentiment.
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
                stroke="#9ca3af" // gray-400
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
                  backgroundColor: "#1f2937", // gray-800
                  borderColor: "#374151", // gray-700
                  borderRadius: "0.5rem",
                  color: "#f9fafb" // gray-50
                }}
                labelStyle={{ color: "#f9fafb" }}
                itemStyle={{ color: "#f9fafb" }}
              />
              <Legend />
              
              {/* 1. Historical Line */}
              <Line
                type="monotone"
                data={historyData}
                dataKey="price"
                stroke="#4f46e5"
                strokeWidth={2}
                name="Historical"
                dot={{ r: 4, fill: "#4f46e5", strokeWidth: 0 }}
                activeDot={{ r: 6 }}
                isAnimationActive={true}
              />
              
              {/* 2. Forecast Line */}
              <Line
                type="monotone"
                data={forecastData}
                dataKey="price"
                stroke="#a78bfa"
                strokeWidth={3}
                name="Forecast"
                strokeDasharray="5 5"
                dot={{ r: 4, fill: "#a78bfa", strokeWidth: 0 }}
                activeDot={{ r: 6 }}
                isAnimationActive={true}
              />

              {/* 3. Connector Line */}
              <Line
                type="monotone"
                data={connectorData}
                dataKey="price"
                stroke="#a78bfa"
                strokeWidth={2}
                strokeDasharray="5 5"
                dot={false}
                legendType="none"
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
