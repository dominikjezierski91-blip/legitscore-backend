import Image from "next/image";

type Props = {
  size?: number;
  className?: string;
};

export function LegitScoreLogo({ size = 80, className }: Props) {
  return (
    <Image
      src="/logo.png"
      alt="LegitScore"
      width={size}
      height={size}
      priority
      className={className}
    />
  );
}
