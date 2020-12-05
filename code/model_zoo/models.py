import segmentation_models_pytorch
from segmentation_models_pytorch.encoders import encoders


DECODERS = ["Unet", "Linknet", "FPN", "PSPNet", "DeepLabV3", "DeepLabV3Plus", "PAN"]
ENCODERS = list(encoders.keys())


def define_model(decoder_name, encoder_name,
                 num_classes=1, activation=None, pretrained='imagenet'):
    """
    Loads a segmentation architecture

    Args:
        decoder_name (str): Decoder name.
        encoder_name (str): Encoder name.
        num_classes (int, optional): Number of classes. Defaults to 1.
        pretrained : pretrained original weights
    Returns:
        torch model -- Pretrained model.
    """
    assert decoder_name in DECODERS, "Decoder name not supported"
    assert encoder_name in ENCODERS, "Encoder name not supported"

    decoder = getattr(segmentation_models_pytorch, decoder_name)

    model = decoder(
        encoder_name,
        encoder_weights=pretrained,
        classes=num_classes,
        activation=activation
    )

    return model