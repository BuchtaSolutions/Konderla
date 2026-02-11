import { SVGProps } from "react";

export type IconSvgProps = SVGProps<SVGSVGElement> & {
  size?: number;
};

export type Project = {
  id: string;
  name: string;
  description?: string;
  created_at?: string;
  rounds?: any[];
}

export type ProjectUpdate = {
  name?: string;
  description?: string;
}
