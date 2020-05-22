# -*- coding: utf-8 -*-

"""Console script for resector."""
import sys
import click
from pathlib import Path


@click.command()
@click.argument('input-path', type=click.Path(exists=True))
@click.argument('parcellation-path', type=click.Path(exists=True))
@click.argument('output-image-path', type=click.Path())
@click.argument('output-label-path', type=click.Path())
@click.option('--min-volume', '-miv', type=int, default=50, show_default=True)
@click.option('--max-volume', '-mav', type=int, default=5000, show_default=True)
def main(
        input_path,
        parcellation_path,
        output_image_path,
        output_label_path,
        min_volume,
        max_volume,
        ):
    """Console script for resector."""
    import torchio
    import resector
    hemispheres = 'left', 'right'
    input_path = Path(input_path)
    output_dir = input_path.parent
    stem = input_path.name.split('.nii')[0]  # assume it's a .nii file

    gm_paths = []
    resectable_paths = []
    for hemisphere in hemispheres:
        dst = output_dir / f'{stem}_gray_matter_{hemisphere}_seg.nii.gz'
        gm_paths.append(dst)
        if not dst.is_file():
            gm = resector.parcellation.get_gray_matter_mask(
                parcellation_path, hemisphere)
            resector.io.write(gm, dst)
        dst = output_dir / f'{stem}_resectable_{hemisphere}_seg.nii.gz'
        resectable_paths.append(dst)
        if not dst.is_file():
            resectable = resector.parcellation.get_resectable_hemisphere_mask(
                parcellation_path,
                hemisphere,
            )
            resector.io.write(resectable, dst)
    noise_path = output_dir / f'{stem}_noise.nii.gz'
    if not noise_path.is_file():
        resector.parcellation.make_noise_image(
            input_path,
            parcellation_path,
            noise_path,
        )

    transform = torchio.Compose((
        torchio.ToCanonical(),
        resector.RandomResection(volumes_range=(min_volume, max_volume)),
    ))
    subject = torchio.Subject(
        image=torchio.Image(input_path, torchio.INTENSITY),
        resection_resectable_left=torchio.Image(resectable_paths[0], torchio.LABEL),
        resection_resectable_right=torchio.Image(resectable_paths[1], torchio.LABEL),
        resection_gray_matter_left=torchio.Image(gm_paths[0], torchio.LABEL),
        resection_gray_matter_right=torchio.Image(gm_paths[1], torchio.LABEL),
        resection_noise=torchio.Image(noise_path, None),
    )
    dataset = torchio.ImagesDataset([subject], transform=transform)
    resected = dataset[0]
    dataset.save_sample(
        resected,
        dict(image=output_image_path, label=output_label_path),
    )

    return 0



        # Assume there is a key 'image' in sample dict
        # Assume there is a key 'resectable_left' in sample dict
        # Assume there is a key 'resectable_right' in sample dict
        # Assume there is a key 'gray_matter_left' in sample dict
        # Assume there is a key 'gray_matter_right' in sample dict
        # Assume there is a key 'noise' in sample dict

if __name__ == "__main__":
    # pylint: disable=no-value-for-parameter
    sys.exit(main())  # pragma: no cover
