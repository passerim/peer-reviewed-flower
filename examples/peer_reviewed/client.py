import argparse

import flwr as fl
from examples.centralized.centralized import Net, load_data, test, train
from examples.centralized.utils import get_parameters, set_parameters, set_seed
from prflwr.peer_review.client import PeerReviewClient
from prflwr.peer_review.config import PrConfig
from torch import nn
from torch.utils.data import DataLoader, Subset
from torch.utils.data.distributed import DistributedSampler

SEED = 0
BATCH_SIZE = 32
DEVICE = "cpu"


class CifarClient(PeerReviewClient):
    def __init__(
        self, model: nn.Module, trainloader: DataLoader, testloader: DataLoader
    ):
        self.model = model
        self.trainloader = trainloader
        self.testloader = testloader

    def get_parameters(self):
        return get_parameters(self.model)

    def train(self, parameters, config):
        set_parameters(self.model, parameters)
        epochs = 1
        if config.get("num_epochs") and isinstance(config.get("num_epochs"), int):
            epochs = config.get["num_epochs"]
        train(self.model, self.trainloader, epochs=epochs, device=DEVICE)
        return get_parameters(self.model), len(self.trainloader.dataset), {}

    def review(self, parameters, config):
        set_parameters(self.model, parameters)
        loss, _ = test(self.model, self.testloader, device=DEVICE)
        return (
            get_parameters(self.model),
            len(self.testloader.dataset),
            {PrConfig.REVIEW_SCORE: float(loss)},
        )

    def evaluate(self, parameters, config):
        set_parameters(self.model, parameters)
        loss, accuracy = test(self.model, self.testloader, device=DEVICE)
        return float(loss), len(self.testloader.dataset), {"accuracy": float(accuracy)}


def setup_client(
    port: int, num_clients: int, partition: int, train_test_fraction: float = 1.0
):
    set_seed(SEED)

    # Load model
    net = Net().to(DEVICE)

    # Load data
    trainset, testset, _ = load_data()
    trainset = Subset(
        trainset, list(range(int(train_test_fraction * trainset.data.shape[0])))
    )
    testset = Subset(
        testset, list(range(int(train_test_fraction * testset.data.shape[0])))
    )
    trainset_sampler = DistributedSampler(
        trainset, num_replicas=num_clients, rank=partition, shuffle=True, seed=SEED
    )
    trainloader = DataLoader(trainset, sampler=trainset_sampler, batch_size=BATCH_SIZE)
    testset_sampler = DistributedSampler(
        testset, num_replicas=num_clients, rank=partition, shuffle=True, seed=SEED
    )
    testloader = DataLoader(testset, sampler=testset_sampler, batch_size=BATCH_SIZE)

    # Start client
    fl.client.start_numpy_client(
        f"localhost:{port}", client=CifarClient(net, trainloader, testloader)
    )


def main():
    """Create model, load data, define Flower client, start Flower client."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, choices=range(0, 65535), required=True)
    parser.add_argument(
        "--num_clients", type=int, choices=range(1, 1000), required=True
    )
    parser.add_argument("--partition", type=int, choices=range(0, 1000), required=True)
    args = parser.parse_args()
    if args.partition >= args.num_clients:
        print(
            "The selected partition of the training data should be an integer lower than the number of clients."
        )
        exit()
    setup_client(args.port, args.num_clients, args.partition)


if __name__ == "__main__":
    main()
