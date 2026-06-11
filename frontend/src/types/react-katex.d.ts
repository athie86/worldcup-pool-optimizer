declare module 'react-katex' {
  import { ComponentType, ReactNode } from 'react';

  export interface MathComponentProps {
    math?: string;
    children?: ReactNode;
    errorColor?: string;
    renderError?: (error: Error | TypeError) => ReactNode;
    settings?: Record<string, unknown>;
    as?: string | ComponentType<unknown>;
  }

  export const InlineMath: ComponentType<MathComponentProps>;
  export const BlockMath: ComponentType<MathComponentProps>;
}
