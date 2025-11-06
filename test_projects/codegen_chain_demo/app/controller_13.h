#pragma once
#include "service_13.h"
#include "model_13.h"
#include <memory>

class Controller13 {
public:
    Controller13();
    void initialize();
    void run();
private:
    std::unique_ptr<Service13> service_;
    std::shared_ptr<Model13> model_;
};
