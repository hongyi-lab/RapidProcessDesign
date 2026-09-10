import type {Metadata} from 'next';
import './globals.css';
export const metadata:Metadata={title:'BWB 工程流程演示',description:'独立本地BWB计算流程、分析收敛与手动设计对比。'};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="zh-CN"><body>{children}</body></html>;}
