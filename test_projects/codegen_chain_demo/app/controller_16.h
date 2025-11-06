#pragma once
#include "service_16.h"
#include "model_16.h"
#include <memory>

class Controller16 {
public:
    Controller16();
    void initialize();
    void run();
private:
    std::unique_ptr<Service16> service_;
    std::shared_ptr<Model16> model_;
};
