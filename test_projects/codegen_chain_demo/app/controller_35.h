#pragma once
#include "service_35.h"
#include "model_35.h"
#include <memory>

class Controller35 {
public:
    Controller35();
    void initialize();
    void run();
private:
    std::unique_ptr<Service35> service_;
    std::shared_ptr<Model35> model_;
};
