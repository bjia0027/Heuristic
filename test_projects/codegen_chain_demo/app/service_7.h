#pragma once
#include <functional>
#include <vector>

class Service7 {
public:
    Service7();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
