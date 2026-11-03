import Image from "next/image";
import type { ImageRef } from "@/lib/types";
import { imageUrl } from "@/lib/images";

export interface PicProps {
  image: ImageRef;
  fill?: boolean;
  sizes?: string;
  className?: string;
  priority?: boolean;
}

/** Wraps next/image with a seeded Lorem Picsum URL. Always emits German alt text. */
export function Pic({ image, fill, sizes, className, priority }: PicProps) {
  const src = imageUrl(image);

  if (fill) {
    return (
      <Image
        src={src}
        alt={image.alt}
        fill
        sizes={sizes ?? "100vw"}
        className={className}
        priority={priority}
      />
    );
  }

  return (
    <Image
      src={src}
      alt={image.alt}
      width={image.width}
      height={image.height}
      sizes={sizes}
      className={className}
      priority={priority}
    />
  );
}

export default Pic;
