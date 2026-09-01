/**
 * مرز خطای سراسری React — به‌جای صفحهٔ سفید، کارت خطای فارسی با دکمهٔ
 * «بارگذاری مجدد» نمایش داده می‌شود.
 */
import { Component, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  message: string;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: '' };

  static getDerivedStateFromError(error: unknown): State {
    return {
      hasError: true,
      message: error instanceof Error ? error.message : String(error),
    };
  }

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-4" dir="rtl">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>خطا در بارگذاری صفحه</CardTitle>
            <CardDescription>
              مشکلی در بارگذاری این بخش پیش آمد. معمولاً با یک بار بارگذاری مجدد برطرف می‌شود.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {this.state.message ? (
              <p className="rounded-md bg-muted p-2 text-xs text-muted-foreground" dir="ltr">
                {this.state.message}
              </p>
            ) : null}
            <div className="flex gap-2">
              <Button className="flex-1" onClick={() => window.location.reload()}>
                بارگذاری مجدد
              </Button>
              <Button
                variant="outline"
                className="flex-1"
                onClick={() => {
                  try {
                    window.localStorage.removeItem('vidara.session.token');
                    window.localStorage.removeItem('vidara.session.user');
                  } catch {
                    /* حالت مرور خصوصی */
                  }
                  window.location.href = '/';
                }}
              >
                خروج و ورود دوباره
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }
}
