import enum
import torch
import numpy as np
import SimpleITK as sitk

from .io import nib_to_sitk
from .resector import _resect


class Hemisphere(enum.Enum):
    LEFT = 'left'
    RIGHT = 'right'


class RandomResection:
    def __init__(
            self,
            volumes_range=None,
            volumes=None,
            sigmas_range=(0.5, 1),
            radii_ratio_range=(0.5, 1.5),
            angles_range=(0, 180),
            delete_keys=True,
            verbose=False,
            ):
        """
        Either volumes or volume_range should be passed
        volumes is an iterable of possible volumes (they come from EPISURG)
        volumes_range is a range for a uniform distribution (TODO: fit a distribution?)

        Assume there is a single channel in sample['image']
        Assume there is a key 'resectable_left' in sample dict
        Assume there is a key 'resectable_right' in sample dict
        Assume there is a key 'gray_matter_left' in sample dict
        Assume there is a key 'gray_matter_right' in sample dict
        Assume there is a key 'noise' in sample dict
        """
        if (volumes is None and volumes_range is None
                or volumes is not None and volumes_range is not None):
            raise ValueError('Please enter a value for volumes or volumes_range')
        self.volumes = volumes
        self.volumes_range = volumes_range
        self.sigmas_range = sigmas_range
        self.radii_ratio_range = radii_ratio_range
        self.angles_range = angles_range
        self.delete_keys = delete_keys
        self.verbose = verbose

    def __call__(self, sample):
        if self.verbose:
            import time
            start = time.time()
        resection_params = self.get_params(
            self.volumes,
            self.volumes_range,
            self.sigmas_range,
            self.radii_ratio_range,
            self.angles_range,
        )
        brain = nib_to_sitk(sample['image'][0], sample['affine'])
        hemisphere = resection_params['hemisphere']
        gray_matter_mask = nib_to_sitk(
            sample[f'gray_matter_{hemisphere}'], sample['affine'])
        resectable_hemisphere_mask = nib_to_sitk(
            sample[f'resectable_{hemisphere}'], sample['affine'])
        noise_image = nib_to_sitk(
            sample['noise'], sample['affine'])
        if self.verbose:
            duration = time.time() - start
            print(f'[Prepare resection images]: {duration:.1f} seconds')

        resected_brain, resection_mask, resection_center = _resect(
            brain,
            gray_matter_mask,
            resectable_hemisphere_mask,
            noise_image,
            resection_params['volume'],
            resection_params['sigmas'],
            resection_params['radii_ratio'],
            resection_params['angles'],
            verbose=self.verbose,
        )
        resection_params['resection_center'] = resection_center
        resected_brain_array = self.sitk_to_array(resected_brain)
        resected_mask_array = self.sitk_to_array(resection_mask)
        image_resected = self.add_channels_axis(resected_brain_array)
        resection_label = self.add_background_channel(resected_mask_array)
        assert image_resected.ndim == 4
        assert resection_label.ndim == 4

        # Update sample
        sample['random_resection'] = resection_params
        sample['image'] = image_resected
        sample['label'] = resection_label

        if self.delete_keys:
            del sample['gray_matter_left']
            del sample['gray_matter_right']
            del sample['resectable_left']
            del sample['resectable_right']
            del sample['noise']

        if self.verbose:
            duration = time.time() - start
            print(f'RandomResection: {duration:.1f} seconds')
        return sample

    @staticmethod
    def get_params(
            volumes,
            volumes_range,
            sigmas_range,
            radii_ratio_range,
            angles_range,
        ):
        # Hemisphere
        hemisphere = Hemisphere.LEFT if RandomResection.flip_coin() else Hemisphere.RIGHT

        # Equivalent sphere volume
        if volumes is None:
            volume = torch.FloatTensor(1).uniform_(*volumes_range).item()
        else:
            index = torch.randint(len(volumes), (1,)).item()
            volume = volumes[index]

        # Sigmas for mask gaussian blur
        sigmas = torch.FloatTensor(3).uniform_(*sigmas_range).tolist()

        # Ratio between two of the radii of the ellipsoid
        radii_ratio = torch.FloatTensor(1).uniform_(*radii_ratio_range).item()

        # Rotation angles of the ellipsoid
        angles = torch.FloatTensor(3).uniform_(*angles_range).tolist()

        parameters = dict(
            hemisphere=hemisphere.value,
            volume=volume,
            sigmas=sigmas,
            radii_ratio=radii_ratio,
            angles=angles,
        )
        return parameters

    @staticmethod
    def flip_coin():
        return torch.rand(1) >= 0.5

    @staticmethod
    def sitk_to_array(image):
        array = sitk.GetArrayFromImage(image)
        return array.transpose(2, 1, 0)

    @staticmethod
    def add_channels_axis(array):
        return array[np.newaxis, ...]

    @staticmethod
    def add_background_channel(foreground):
        background = 1 - foreground
        return np.stack((background, foreground))
