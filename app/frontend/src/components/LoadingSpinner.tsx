import React from 'react';

interface LoadingSpinnerProps {
  message?: string;
}

/** نشانگر بارگذاری سراسری؛ رنگ‌ها فقط از توکن‌های تم برند خوانده می‌شوند. */
const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  message = 'در حال بارگذاری…',
}) => {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="text-center">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        <p className="mt-4 text-muted-foreground">{message}</p>
      </div>
    </div>
  );
};

export default LoadingSpinner;